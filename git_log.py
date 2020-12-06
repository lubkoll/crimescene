from collections import defaultdict
import re
import subprocess

from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Dict, Iterable, List, Set
import miner.complexity_calculations as complexity_calculations

DATE_FORMAT = '%Y-%m-%d'


class DescriptiveStats:
    def __init__(self, name, all_values):
        self.name = name
        self._all_values = all_values
        self.total = sum(all_values)
        self.n_revs = len(all_values)

    def mean(self):
        return self.total / float(self._protected_n())

    def max_value(self):
        try:
            return max(self._all_values)
        except ValueError:
            return 0

    def min_value(self):
        try:
            return min(self._all_values)
        except ValueError:
            return 0

    def sd(self):
        from math import sqrt
        std = 0
        mean = self.mean()
        for a in self._all_values:
            std = std + (a - mean)**2
        std = sqrt(std / float(self._protected_n()))
        return std

    def _protected_n(self):
        n = self.n_revs
        return max(n, 1)


def as_stats(revision, complexity_by_line):
    return DescriptiveStats(revision, complexity_by_line)


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
    parent_shas: list = field(default_factory=list)
    child_shas: list = field(default_factory=list)
    parents: Iterable = field(default_factory=list)
    children: Iterable = field(default_factory=list)
    creation_time: datetime = datetime(year=2015,
                                       month=1,
                                       day=1,
                                       tzinfo=timezone.utc)
    author: str = ''
    msg: str = ''
    changes: Iterable[Change] = field(default_factory=list)


def get_commit(line: str) -> Commit:
    commit_match = re.match(
        r"'\[(\w+)\]\s+\[(.*)\]\s+(\w.*\w)\s+(\d{4}-\d{2}-\d{2}\s+\d{2}:\d{2}:\d{2}\s+[\+\-]*\d{4})\s+(\S.*)",
        #        r"'\[(\w+)\]\s+(\w.*\w)\s+(\d{4})-(\d{2})-(\d{2})\s+(\d{2}):(\d{2}):(\d{2})\s+\+(\d{4})\s+(\S.*)",
        line)
    if not commit_match:
        print(f'Failed to match commit in: {line}')
        return None
    # offset = int(commit_match.group(9))
    # dhours = int(offset / 100)
    # dminutes = offset % 100

    creation_time = datetime.strptime(commit_match.group(4),
                                      '%Y-%m-%d %H:%M:%S %z')
    # creation_time = datetime(year=int(commit_match.group(3)),
    #                          month=int(commit_match.group(4)),
    #                          day=int(commit_match.group(5)),
    #                          hour=int(commit_match.group(6)) - dhours,
    #                          minute=int(commit_match.group(7)) - dminutes,
    #                          second=int(commit_match.group(8)),
    #                          tzinfo=timezone.utc)
    return Commit(sha=commit_match.group(1),
                  parent_shas=commit_match.group(2).split(' '),
                  author=commit_match.group(3),
                  creation_time=creation_time,
                  msg=commit_match.group(5).replace("'", ""))


# Algorithms/Adapter/FEniCS/operator.hh => VSA/Adapter/FEniCS/c1Operator.hh


def get_change(line: str) -> Change:
    change_match = re.match(r'([0-9]+)\s+([0-9]+)\s+(\S+.*)', line)
    if change_match:
        old_name = ''
        name = change_match.group(3)

        if '=>' in name:
            mapping_regex = r'.*(\{\S*\s*=>\s*\S*\})(.*)' if '{' in name else r'(\S*\s*=>\s*\S*)'
            mapping_match = re.match(mapping_regex, name)
            if mapping_match:
                mapping = mapping_match.group(1)
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

    for commit in commits:
        for parent_sha in commit.parent_shas:
            for parent in commits:
                if parent.sha == parent_sha:
                    parent.children.append(commit)
                    parent.child_shas.append(commit.sha)
                    commit.parents.append(parent)

    return commits


def _run_cmd(root, args):
    return subprocess.Popen(args, stdout=subprocess.PIPE,
                            cwd=root).communicate()[0].decode("utf-8")


def get_full_log(root: str):
    return _run_cmd(root, [
        'git', 'log', "--pretty=format:'[%h] [%p] %aN %cd %s'", '--date=iso',
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


class ForwardTraversal:
    def __init__(self, git_log, op, valid_cond=None, break_cond=None) -> None:
        self._log = git_log
        self._op = op
        self._valid_cond = valid_cond
        self._break_cond = break_cond
        if not self._valid_cond:
            self._valid_cond = lambda _: True
        if not self._break_cond:
            self._break_cond = lambda _: False

    def _iter(self, commit: Commit, visited: Dict[str, Set], child_sha=''):
        visited[commit.sha].add(child_sha)
        if visited[commit.sha] != set(commit.parent_shas):
            return []

        if self._break_cond(commit):
            return

        if self._valid_cond(commit):
            self._op(commit)

        for child in commit.children:
            self._iter(commit=child, visited=visited, child_sha=commit.sha)

    def __call__(self) -> None:
        visited = {commit.sha: set() for commit in self._log.commits}
        commit = self._log.commits[0]
        self._iter(commit=commit, visited=visited)


class BackwardTraversal:
    def __init__(self, git_log, op, valid_cond=None, break_cond=None) -> None:
        self._log = git_log
        self._op = op
        self._valid_cond = valid_cond
        self._break_cond = break_cond
        if not self._valid_cond:
            self._valid_cond = lambda _: True
        if not self._break_cond:
            self._break_cond = lambda _: False

    def _iter(self, commit: Commit, visited: Dict[str, Set], parent_sha=None):
        if parent_sha is not None:
            visited[commit.sha].add(parent_sha)
        if visited[commit.sha] != set(commit.child_shas):
            return []

        if self._break_cond(commit):
            return

        if self._valid_cond(commit):
            self._op(commit)

        for parent in commit.parents:
            self._iter(commit=parent, visited=visited, parent_sha=commit.sha)

    def __call__(self) -> None:
        visited = {commit.sha: set() for commit in self._log.commits}
        commit = self._log.commits[-1]
        self._iter(commit=commit, visited=visited)


class GitLog:
    def __init__(self, root: str, commits) -> None:
        self.root = root
        self._commits: List[Commit] = commits
        self._sha2commit = {commit.sha: commit for commit in commits}
        # for commit in commits:
        #     print(
        #         f'{commit.sha} -> {[parent for parent in commit.parent_shas]}')

    def get_commit_from_sha(self, sha: str) -> Commit:
        return self._sha2commit[sha]

    @property
    def commits(self):
        return self._commits

    def first_commit_date(self):
        return self.commits[0].creation_time

    def first_commit_sha(self):
        return self.commits[0].sha

    def last_commit_sha(self):
        return self.commits[-1].sha

    def commit_msg(self, begin: datetime, end: datetime):
        return [
            commit.msg for commit in self.commits
            if begin <= commit.creation_time <= end
        ]

    @classmethod
    def from_dir(_cls, dir: str):
        return GitLog(root=dir,
                      commits=sorted(get_commit_list(get_full_log(root=dir)),
                                     key=lambda commit: commit.creation_time))

    # def get_stats(self, begin: datetime, end: datetime):
    #     stats = {}
    #     return stats

    def get_churn(self):
        churn = defaultdict(list)
        for commit in self.commits:
            for change in commit.changes:
                if change.old_filename:
                    if change.old_filename not in churn:
                        continue
                    churn[change.filename] = churn.pop(change.old_filename)
                churn[change.filename].append(
                    (commit.creation_time, change.added_lines,
                     change.removed_lines))
        return churn

    def _in_interval(self, begin: datetime, end: datetime):
        def in_interval(commit):
            return begin <= commit.creation_time <= end

        return in_interval

    def get_churn_for(self, filename: str, begin: datetime, end: datetime):
        churn = []

        def op(commit):
            nonlocal filename
            for change in commit.changes:
                if change.filename == filename:
                    churn.append(
                        (commit.sha, change.added_lines, change.removed_lines))
                    if change.old_filename:
                        filename = change.old_filename

        BackwardTraversal(git_log=self,
                          op=op,
                          valid_cond=self._in_interval(begin=begin, end=end))()
        return list(reversed(churn))

    def get_couplings(self, filename: str, begin: datetime, end: datetime):
        n_rev = 0
        couplings = defaultdict(lambda: {'count': 0, 'names': set()})

        def op(commit):
            nonlocal filename
            nonlocal n_rev
            files_in_commit = [change.filename for change in commit.changes]
            new_filename = filename
            if filename in files_in_commit:
                n_rev += 1
                for change in commit.changes:
                    if change.filename == filename:
                        if change.old_filename:
                            new_filename = change.old_filename
                    else:
                        found = False
                        for data in couplings.values():
                            if change.filename in data['names']:
                                data['count'] += 1
                                if change.old_filename:
                                    data['names'].add(change.old_filename)
                                    found = True

                        if not found:
                            couplings[change.filename]['names'].add(
                                change.filename)
                            couplings[change.filename]['count'] += 1
                            if change.old_filename:
                                couplings[change.filename]['names'].add(
                                    change.old_filename)
            filename = new_filename

        BackwardTraversal(git_log=self,
                          op=op,
                          valid_cond=self._in_interval(begin=begin, end=end))()

        couplings = {
            name: data['count']
            for name, data in couplings.items()
            if data['count'] > 2 and data['count'] / n_rev > 0.2
        }
        return couplings, n_rev

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

        def op(commit):
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

        # ForwardTraversal(git_log=self,
        #                  op=op,
        #                  valid_cond=self._in_interval(begin, end))()

        for commit in self._commits:
            if begin > commit.creation_time:
                continue
            if end < commit.creation_time:
                break
            op(commit)

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

    def get_commits_for_file(self, filename: str, begin: datetime,
                             end: datetime):
        commits = []

        def op(commit):
            nonlocal filename
            for change in commit.changes:
                if change.filename == filename:
                    commits.append((commit, filename))
                    if change.old_filename:
                        filename = change.old_filename
                    return

        BackwardTraversal(git_log=self,
                          op=op,
                          valid_cond=self._in_interval(begin=begin, end=end))()
        return commits

    def calculate_complexity_over_range(self, filename: str, begin: datetime,
                                        end: datetime):
        commits = self.get_commits_for_file(filename=filename,
                                            begin=begin,
                                            end=end)
        complexity_by_rev = []
        for commit, commit_filename in commits:
            historic_version = _run_cmd(
                self.root, ['git', 'show', commit.sha + ':' + commit_filename])
            complexity_by_line = complexity_calculations.calculate_complexity_in(
                historic_version)
            complexity_by_rev.append((as_stats(commit.sha,
                                               complexity_by_line)))

        return list(reversed(complexity_by_rev))

    def compute_complexity_trend(self, filename: str, begin: datetime,
                                 end: datetime):
        complexity_trend = self.calculate_complexity_over_range(
            filename=filename, begin=begin, end=end)
        return [[
            stats.name, stats.n_revs, stats.total,
            round(stats.mean(), 2),
            round(stats.sd(), 2)
        ] for stats in complexity_trend]
