from time import timezone
from analyze_git_log import DATE_FORMAT
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import date, datetime, timezone, tzinfo
import time
import re
import subprocess
from typing import Dict, Iterable, List


@dataclass
class Change:
    old_filename: str = ''
    filename: str = ''
    added_lines: int = 0
    removed_lines: int = 0

    def __str__(self) -> str:
        return f'Change(old_filename={self.old_filename}, filename={self.filename}, added_lines={self.added_lines}, removed_lines={self.removed_lines})'


@dataclass
class Commit:
    sha: str = ''
    creation_time: datetime = datetime(year=2015,
                                       month=1,
                                       day=1,
                                       tzinfo=timezone.utc)
    author: str = ''
    msg: str = ''
    changes: Iterable[Change] = field(default_factory=list)

    def __str__(self) -> str:
        return f'[{self.sha}] {self.author} {self.creation_time} {self.msg}\n{self.changes}'


def _as_rev_range(start, end):
    return start + '..' + end


def _run_cmd(root, args):
    return subprocess.Popen(args, stdout=subprocess.PIPE,
                            cwd=root).communicate()[0].decode("utf-8")


def get_log(root: str, after: str, before: str):
    return _run_cmd(root, [
        'git', 'log', "--pretty=format:'[%h] %an %ad %s'", '--date=short',
        f'--after={after}', f'--before={before}', '--numstat'
    ])


def get_first_commit_date(root: str):
    return datetime.strptime(
        _run_cmd(root, ['git', 'log', '--pretty=format:"%ad"', '--date=short'
                        ]).split('\n')[-1].replace('"', ''), DATE_FORMAT)


def get_first_commit_sha(root: str):
    return _run_cmd(root, ['git', 'rev-list', 'HEAD']).split('\n')[-2]


def get_last_commit_sha(root: str):
    return _run_cmd(root, ['git', 'rev-parse', 'HEAD']).split('\n')[-2]


def get_loc(root: str, before: str):
    before_sha = _run_cmd(
        root,
        ['git', 'rev-list', '-n 1', f'--before={before}', 'master']).replace(
            '\n', '')
    _run_cmd(root, ['git', 'checkout', before_sha])
    loc = _run_cmd(root, [
        'cloc', './', '--unix', '--by-file', '--csv', '--quiet',
        '--exclude-dir=build,build-Release'
    ])
    _run_cmd(root, ['git', 'checkout', 'master'])
    return loc


def get_commit(line: str) -> Commit:
    commit_match = re.match(
        r"'\[(\w+)\]\s+(\w.*\w)\s+(\d{4})-(\d{2})-(\d{2})\s+(\S.*)", line)
    if not commit_match:
        print(f'Failed to match commit in: {line}')
        return None
    creation_time = datetime(year=int(commit_match.group(3)),
                             month=int(commit_match.group(4)),
                             day=int(commit_match.group(5)),
                             tzinfo=timezone.utc)
    return Commit(sha=commit_match.group(1),
                  author=commit_match.group(2),
                  creation_time=creation_time,
                  msg=commit_match.group(6))


def get_change(line: str) -> Change:
    change_match = re.match(r'([0-9]+)\s+([0-9]+)\s+(\S+.*)', line)
    if change_match:
        name = change_match.group(3)

        mapping_match = re.match(r'.*(\{\S*\s*=>\s*\S*\})(.*)', name)
        old_name = ''
        if mapping_match:
            mapping = mapping_match.group(1)
            rename_match = re.match(r'\{(\S*)\s*=>\s*(\S*)\}', mapping)
            # case: new folder introduced
            if rename_match.group(1):
                old_name = name.replace(mapping, rename_match.group(1))
            else:
                old_name = name.replace('/' + mapping, '')
            if rename_match.group(2):
                name = name.replace(mapping, rename_match.group(2))
            else:
                name = name.replace('/' + mapping, '')
        return Change(old_filename=old_name,
                      filename=name,
                      added_lines=int(change_match.group(1)),
                      removed_lines=int(change_match.group(2)))


def get_commit_list(git_log: str) -> List[Commit]:
    lines = git_log.split('\n')
    commits = []
    current_commit = None
    for line in lines:
        if not line:
            continue
        if line.startswith("'["):
            if current_commit:
                commits.append(current_commit)
                current_commit = None
            current_commit = get_commit(line)
            continue

        if current_commit:
            change = get_change(line)
            if change:
                current_commit.changes.append(change)

    if current_commit:
        commits.append(current_commit)

    return commits


def get_revisions(git_log: str) -> Dict[str, int]:
    commits = sorted(get_commit_list(git_log),
                     key=lambda commit: commit.creation_time)

    revisions = defaultdict(
        lambda: {
            'revisions':
            0,
            'soc':
            0,
            'last_change':
            datetime(year=2015, month=1, day=1, tzinfo=timezone.utc).timestamp(
            ),
            'churn': []
        })
    couplings = defaultdict(lambda: defaultdict(int))

    def update_couplings(names_in_commit):
        soc = len(names_in_commit)
        for name in names_in_commit:
            revisions[name]['soc'] += soc
            for other_name in names_in_commit:
                if name != other_name:
                    couplings[name][other_name] += 1
            couplings[name]['count'] += 1

    for commit in commits:
        for change in commit.changes:
            if change.old_filename:
                revisions[change.filename] = revisions[change.old_filename]
                revisions.pop(change.old_filename)
            revisions[change.filename]['revisions'] += 1
            revisions[change.filename][
                'last_change'] = commit.creation_time.timestamp()
            revisions[change.filename]['churn'].append({
                'timestamp':
                revisions[change.filename]['last_change'],
                'added_lines':
                change.added_lines,
                'removed_lines':
                change.removed_lines
            })
        update_couplings([change.filename for change in commit.changes])

    return revisions, couplings


def get_authors(root: str, filename: str):
    authors = defaultdict(int)
    author_summary = _run_cmd(
        root, ['git', 'shortlog', '-s', '-n', '--', filename]).split('\n')
    for line in author_summary:
        if line:
            match = re.match(r'\s+(\d+)\s+(\w.*\w)', line)
            authors[match.group(2)] = int(match.group(1))
    return authors


def get_main_authors(root: str, filename: str, max_authors: int = 3):
    authors = get_authors(root=root, filename=filename)
    valid = sorted(authors.values(), reverse=True)
    n_authors = len(valid)
    if len(valid) > max_authors:
        valid = valid[:max_authors]
    to_remove = [author for author in authors if authors[author] not in valid]
    for author in to_remove:
        authors.pop(author)
    return authors, n_authors


def add_repo_main_authors(root: str, stats, max_authors: int = 3):
    for module in stats:
        stats[module]['authors'] = get_main_authors(root=root,
                                                    filename=module,
                                                    max_authors=max_authors)


def get_summary(git_log: str) -> int:
    authors = set()
    n_revisions = 0
    lines = git_log.split('\n')
    for line in lines:
        if not line.startswith("'["):
            continue
        n_revisions += 1
        match = re.match(r"'\[\w+\]\s+(\w.*\w)\s+\d{4}-\d{2}-\d{2}.*", line)
        authors.add(match.group(1))
    return {'#authors': len(authors), '#revisions': n_revisions}


def add_loc(revisions, locs):
    lines = locs.split('\n')
    for line in lines:
        if not line:
            continue

        entries = line.split(',')
        name = entries[1]
        if name == 'filename':
            continue
        name = name[2:]
        revisions[name]['loc'] = int(entries[4])

    to_remove = [name for name, data in revisions.items() if 'loc' not in data]
    for name in to_remove:
        del revisions[name]


def read_commit_messages(root, start: str, end: str):
    return _run_cmd(root, [
        'git', 'log', "--pretty=format:'%s'", f'--after={start}',
        f'--before={end}'
    ]).replace('\n', ' ').replace("'", "")


if __name__ == "__main__":
    start = time.time()
    root = '/home/lars/projects/Spacy'
    git_log = get_log(root=root, after='2018-09-01', before='2019-01-01')
    get_authors(root=root, filename='CMakeLists.txt')
