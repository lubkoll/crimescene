from collections import defaultdict
import re
import subprocess

from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Dict, Iterable, List

DATE_FORMAT = '%Y-%m-%d'


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


def get_commit(line: str) -> Commit:
    commit_match = re.match(
        r"'\[(\w+)\]\s+(\w.*\w)\s+(\d{4}-\d{2}-\d{2}\s+\d{2}:\d{2}:\d{2}\s+[\+\-]*\d{4})\s+(\S.*)",
        #        r"'\[(\w+)\]\s+(\w.*\w)\s+(\d{4})-(\d{2})-(\d{2})\s+(\d{2}):(\d{2}):(\d{2})\s+\+(\d{4})\s+(\S.*)",
        line)
    if not commit_match:
        print(f'Failed to match commit in: {line}')
        return None
    # offset = int(commit_match.group(9))
    # dhours = int(offset / 100)
    # dminutes = offset % 100

    creation_time = datetime.strptime(commit_match.group(3),
                                      '%Y-%m-%d %H:%M:%S %z')
    # creation_time = datetime(year=int(commit_match.group(3)),
    #                          month=int(commit_match.group(4)),
    #                          day=int(commit_match.group(5)),
    #                          hour=int(commit_match.group(6)) - dhours,
    #                          minute=int(commit_match.group(7)) - dminutes,
    #                          second=int(commit_match.group(8)),
    #                          tzinfo=timezone.utc)
    return Commit(sha=commit_match.group(1),
                  author=commit_match.group(2),
                  creation_time=creation_time,
                  msg=commit_match.group(4))


# Algorithms/Adapter/FEniCS/operator.hh => VSA/Adapter/FEniCS/c1Operator.hh


def get_change(line: str) -> Change:
    change_match = re.match(r'([0-9]+)\s+([0-9]+)\s+(\S+.*)', line)
    if change_match:
        old_name = ''
        name = change_match.group(3)

        if '=>' in name:
            full_rename = '{' not in name
            if full_rename:
                print(f'NAME {name}')
            mapping_regex = r'.*(\{\S*\s*=>\s*\S*\})(.*)' if '{' in name else r'(\S*\s*=>\s*\S*)'
            mapping_match = re.match(mapping_regex, name)
            if mapping_match:
                mapping = mapping_match.group(1)
                if full_rename:
                    print(f'map: {mapping}')
                rename_regex = r'\{(\S*)\s*=>\s*(\S*)\}' if '{' in name else r'(\S*)\s*=>\s*(\S*)'
                rename_match = re.match(rename_regex, mapping)
                # case: new folder introduced
                if rename_match.group(1):
                    old_name = name.replace(mapping, rename_match.group(1))
                else:
                    old_name = name.replace('/' + mapping, '')
                if rename_match.group(2):
                    name = name.replace(mapping, rename_match.group(2))
                else:
                    name = name.replace('/' + mapping, '')
                if full_rename:
                    print(f'REAME {old_name} -> {name}')
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
                if change.filename == 'VSA/Adapter/FEniCS/c1Operator.hh':
                    print(current_commit.sha)
                    print(change)
                # if current_commit.sha == 'bd1a5dcc':
                #     print(f'C {change}')
                current_commit.changes.append(change)

    if current_commit:
        commits.append(current_commit)

    return commits


def _run_cmd(root, args):
    return subprocess.Popen(args, stdout=subprocess.PIPE,
                            cwd=root).communicate()[0].decode("utf-8")


def get_full_log(root: str):
    return _run_cmd(root, [
        'git', 'log', "--pretty=format:'[%h] %an %cd %s'", '--date=iso',
        '--numstat', '--topo-order'
    ])


def get_first_commit_date(root: str):
    return datetime.strptime(
        _run_cmd(root, ['git', 'log', '--pretty=format:"%cd"', '--date=short'
                        ]).split('\n')[-1].replace('"', ''), DATE_FORMAT)


def get_first_commit_sha(root: str):
    return _run_cmd(root, ['git', 'rev-list', 'HEAD']).split('\n')[-2]


def get_last_commit_sha(root: str):
    return _run_cmd(root, ['git', 'rev-parse', 'HEAD']).split('\n')[-2]


class GitLog:
    def __init__(self, commits) -> None:
        self._commits: List[Commit] = commits
        print(f'init git log with {len(commits)} commits')
        for commit in commits:
            #            if commit.sha in ['91db177d', 'bd1a5dcc']:
            if commit.sha in ['91db177d']:
                print(commit.sha)
                print(commit.creation_time)
                print(commit.msg)
                print(len(commit.changes))
                # for i in range(20):
                #     print(commit.changes[143 + i])
                print('===')
                for change in commit.changes:
                    if 'linearBlockOperator' in change.filename:
                        print(change)
                        print(commit.changes.index(change))

    def first_commit_date(self):
        return self._commits[0].creation_time

    def first_commit_sha(self):
        return self._commits[0].sha

    def last_commit_sha(self):
        return self._commits[-1].sha

    def commit_msg(self, begin: datetime, end: datetime):
        return [
            commit.msg for commit in self._commits
            if begin <= commit.creation_time <= end
        ]

    @classmethod
    def from_dir(_cls, dir: str):
        return GitLog(commits=sorted(get_commit_list(get_full_log(root=dir)),
                                     key=lambda commit: commit.creation_time))

    # def get_stats(self, begin: datetime, end: datetime):
    #     stats = {}
    #     return stats

    def get_churn(self):
        churn = defaultdict(list)
        for commit in self._commits:
            for change in commit.changes:
                if change.old_filename:
                    if change.old_filename not in churn:
                        continue
                    churn[change.filename] = churn.pop(change.old_filename)
                churn[change.filename].append(
                    (commit.creation_time, change.added_lines,
                     change.removed_lines))
        return churn

    def get_churn_for(self, filename: str, begin: datetime, end: datetime):
        churn = []
        for commit in reversed(self._commits):
            if commit.creation_time > end:
                continue
            if commit.creation_time < begin:
                break
            for change in commit.changes:
                if filename == change.filename:
                    churn.append((commit.sha, commit.creation_time, commit.msg,
                                  change.added_lines, change.removed_lines))
                    if change.old_filename:
                        filename = change.old_filename
        return churn

    def get_revisions(self, begin: datetime, end: datetime):
        revisions = defaultdict(
            lambda: {
                'revisions':
                0,
                'soc':
                0,
                'last_change':
                datetime(year=2015, month=1, day=1, tzinfo=timezone.utc).
                timestamp(),
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

        for commit in self._commits:
            if commit.sha == '91db177d':
                print('1')
            if begin > commit.creation_time:
                if commit.sha == '91db177d':
                    print('2')
                continue
            if end < commit.creation_time:
                if commit.sha == '91db177d':
                    print('3')
                break
            for change in commit.changes:
                if change.old_filename:
                    revisions[change.filename] = revisions[change.old_filename]
                    revisions.pop(change.old_filename)
                revisions[change.filename]['revisions'] += 1
                revisions[change.filename][
                    'last_change'] = commit.creation_time.timestamp()
                if 'linearBlockOperator' in change.filename:
                    if commit.sha == '91db177d':
                        print('rev')
                        print(change)
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

    def get_authors(self, filename: str):
        added_lines = 0
        authors = defaultdict(int)
        for commit in reversed(self._commits):
            for change in commit.changes:
                if filename == change.filename:
                    added_lines += change.added_lines
                    authors[commit.author] += change.added_lines
                    if change.old_filename:
                        filename = change.old_filename
        for author in authors:
            authors[author] = authors[author] / added_lines
        return authors

    def get_main_authors(self, filename: str, max_authors: int = 3):
        authors = self.get_authors(filename=filename)
        valid = sorted(authors.values(), reverse=True)
        n_authors = len(valid)
        if len(valid) > max_authors:
            valid = valid[:max_authors]
        to_remove = [
            author for author in authors if authors[author] not in valid
        ]
        for author in to_remove:
            authors.pop(author)
        return authors, n_authors
