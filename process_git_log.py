from analyze_git_log import DATE_FORMAT
from collections import defaultdict
from datetime import datetime
import time
import re
import subprocess
from typing import Dict


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


def get_revisions(git_log: str) -> Dict[str, int]:
    lines = git_log.split('\n')
    commits = []
    for line in lines:
        if not line:
            continue
        if line.startswith("'["):
            commits.append(line)
            continue
        commits[-1] += '\n' + line

    revisions = defaultdict(lambda: {'revisions': 0, 'soc': 0})
    couplings = defaultdict(lambda: defaultdict(int))
    names_in_commit = []
    commits.reverse()
    for commit in commits:
        lines = commit.split('\n')
        for line in lines:
            if line.startswith("'["):
                soc = len(names_in_commit)
                for name in names_in_commit:
                    revisions[name]['soc'] += soc
                    for other_name in names_in_commit:
                        if name != other_name:
                            couplings[name][other_name] += 1
                    couplings[name]['count'] += 1

                names_in_commit = []
                continue

            def add_name(name):
                revisions[name]['revisions'] += 1
                names_in_commit.append(name)

            match = re.match(r'[0-9]+\s+[0-9]+\s+(\S+.*)', line)
            if match:
                name = match.group(1)

                mapping_match = re.match(r'(.*)(\{\S+\s*=>\s*\S+\})(.*)', name)
                if mapping_match:
                    mapping = mapping_match.group(2)
                    rename_match = re.match(r'\{(\S+)\s*=>\s*(\S+)\}', mapping)
                    old_name = name.replace(mapping, rename_match.group(1))
                    new_name = name.replace(mapping, rename_match.group(2))
                    if old_name in revisions:
                        prev = revisions.pop(old_name)
                        revisions[new_name]['revisions'] += prev['revisions']
                    add_name(new_name)
                    continue

                add_name(name)

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

    # blame_lines = _run_cmd(root, ['git', 'blame', filename]).split('\n')
    # authors = defaultdict(int)
    # for line in blame_lines:
    #     if line:
    #         match = re.match(r'.*\((\w.*\w)\s+\d{4}-\d{2}-\d{2}.*', line)
    #         authors[match.group(1)] += 1
    # return authors


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
