from collections import defaultdict
from git_data import Commit, get_commit_list
from desc_stats import DescriptiveStats, as_stats, dict_as_stats
from process_git_log import read_diff_for
from git_proximity_analysis import parse_changes_per_file_in
import os
import subprocess

from datetime import datetime, timezone
from typing import Dict, List, Set
import miner.complexity_calculations as complexity_calculations
from util import DATE_FORMAT


def sum_proximity_stats(all_proximities):
    """ Received all proximities as a list of dictionaries.
        Each dictionary represents the proximities in the changed 
        in one revision.
        Take this list and group all changes per item.
    """
    all_grouped = defaultdict(list)
    for one_rev_proximity in all_proximities:
        for one_file, proximity in one_rev_proximity.items():
            all_grouped[one_file].append(proximity)
    return dict_as_stats(all_grouped)


def _run_cmd(root, args):
    return subprocess.Popen(args, stdout=subprocess.PIPE,
                            cwd=root).communicate()[0].decode("utf-8")


def get_full_log(root: str):
    return _run_cmd(root, [
        'git', 'log', "--pretty=format:'[%h] [%p] %aN %cd %s'", '--date=iso',
        '--numstat', '--topo-order'
    ])


def get_log_after_revision(root: str, sha: str):
    return _run_cmd(root=root,
                    args=[
                        'git', 'log', "--pretty=format:'[%h] [%p] %aN %cd %s'",
                        '--date=iso', '--numstat', '--topo-order',
                        f'{sha}..HEAD'
                    ])


def get_files_in_repository(root: str):
    return _run_cmd(root=root,
                    args=['git', 'ls-tree', '-r', 'master',
                          '--name-only']).split('\n')


def get_first_commit_date(root: str):
    return datetime.strptime(
        _run_cmd(root, ['git', 'log', '--pretty=format:"%cd"', '--date=short'
                        ]).split('\n')[-1].replace('"', ''), DATE_FORMAT)


def get_first_commit_sha(root: str):
    return _run_cmd(root, ['git', 'rev-list', 'HEAD']).split('\n')[-2]


def get_last_commit_sha(root: str):
    return _run_cmd(root, ['git', 'rev-parse', 'HEAD']).split('\n')[-2]


class ForwardTraversal:
    def __init__(self, commits, op, valid_cond=None, break_cond=None) -> None:
        self._commits = commits
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
        visited = {commit.sha: set() for commit in self._commits}
        commit = self._commits[0]
        self._iter(commit=commit, visited=visited)


class BackwardTraversal:
    def __init__(self, commits, op, valid_cond=None, break_cond=None) -> None:
        self._commits = commits
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
        visited = {commit.sha: set() for commit in self._commits}
        commit = self._commits[-1]
        self._iter(commit=commit, visited=visited)


def get_files_in_commit(root: str, sha: str):
    files = _run_cmd(root,
                     ['git', 'ls-tree', '-r', '--name-only', sha]).split('\n')
    to_remove = [file for file in files if file.endswith('.enc')]
    for file in to_remove:
        files.remove(file)
    return files


def get_lines_in_sha(root: str, sha: str):
    files = get_files_in_commit(root=root, sha=sha)
    return sum(
        complexity_calculations.compute_lines(
            _run_cmd(root, ['git', 'show', f'{sha}:{file}']))
        for file in files)


def get_lines_before(root: str, before: datetime):
    sha = _run_cmd(root, [
        'git', 'rev-list', '-1', "--pretty=format:'%h'",
        f'--before={before.strftime(DATE_FORMAT)}', 'master'
    ]).split('\n')[1].replace("'", "")
    return get_lines_in_sha(root=root, sha=sha)


def _pdistance(positions):
    return sum([j - i for i, j in zip(positions[:-1], positions[1:])])


def calc_proximity(changes):
    return dict([(name, _pdistance(change))
                 for name, change in changes.items()])


def in_interval(begin: datetime, end: datetime):
    def in_interval(commit):
        return begin <= commit.creation_time <= end

    return in_interval


class GitLog:
    def __init__(self, root: str, commits) -> None:
        self.root = root
        self._commits: List[Commit] = commits
        self._sha2commit = {commit.sha: commit for commit in commits}
        self._sha2time = {
            commit.sha: commit.creation_time
            for commit in commits
        }
        # for commit in commits:
        #     print(
        #         f'p0 {commit.sha} -> {[parent for parent in commit.parent_shas]}')
        #     print(
        #         f'p1 {commit.sha} -> {[parent.sha for parent in commit.parents]}')
        #     print(f'c0 {commit.sha} -> {[child for child in commit.child_shas]}')
        #     print(
        #         f'c1 {commit.sha} -> {[child.sha for child in commit.children]}')

    def get_commit_from_sha(self, sha: str) -> Commit:
        return self._sha2commit[sha]

    def get_time_from_sha(self, sha: str) -> datetime:
        return self._sha2time[sha]

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
                      commits=get_commit_list(get_full_log(root=dir)))

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

        BackwardTraversal(commits=self._commits,
                          op=op,
                          valid_cond=in_interval(begin=begin, end=end))()
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

        BackwardTraversal(commits=self._commits,
                          op=op,
                          valid_cond=in_interval(begin=begin, end=end))()

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
                'churn': [],
                'proximity':
                0.0,
                'mean_proximity':
                0.0,
                'proximity_sd':
                0.0,
                'proximity_max':
                0.0
            })

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
            names_in_commit = [change.filename for change in commit.changes]
            soc = len(names_in_commit) - 1
            for name in names_in_commit:
                revisions[name]['soc'] += soc

        # ForwardTraversal(commits=self._commits,
        #                  op=op,
        #                  valid_cond=in_interval(begin, end))()

        for commit in self._commits:
            if begin > commit.creation_time:
                continue
            if end < commit.creation_time:
                break
            op(commit)

        return revisions

    def get_revisions_only(self, begin: datetime, end: datetime):
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
            names_in_commit = [change.filename for change in commit.changes]
            soc = len(names_in_commit) - 1
            for name in names_in_commit:
                revisions[name]['soc'] += soc

        # ForwardTraversal(commits=self._commits,
        #                  op=op,
        #                  valid_cond=in_interval(begin, end))()

        for commit in self._commits:
            if begin > commit.creation_time:
                continue
            if end < commit.creation_time:
                break
            op(commit)

        return revisions

    def get_revisions_for_module(self, begin: datetime, end: datetime,
                                 module_map):
        '''
            Does not trace renamings.
        '''
        revisions = defaultdict(
            lambda: {
                'revisions':
                0,
                'soc':
                0,
                'loc':
                0,
                'last_change':
                datetime(year=2015, month=1, day=1, tzinfo=timezone.utc).
                timestamp(),
                'churn': [],
                'lines':
                0,
                'complexity':
                0.0,
                'mean_complexity':
                0.0,
                'complexity_sd':
                0.0,
                'complexity_max':
                0.0
            })

        def op(commit):
            modules_in_commit = {
                module_map(change.filename)
                for change in commit.changes
            }
            for module in modules_in_commit:
                revisions[module]['revisions'] += 1
                revisions[module][
                    'last_change'] = commit.creation_time.timestamp()

                churn = {
                    'timestamp': commit.creation_time.timestamp(),
                    'added_lines': 0,
                    'removed_lines': 0
                }
                for change in commit.changes:
                    if module == module_map(change.filename):
                        churn['added_lines'] += change.added_lines
                        churn['removed_lines'] += change.removed_lines
                revisions[module]['churn'].append(churn)
            soc = len(modules_in_commit) - 1
            for module in modules_in_commit:
                revisions[module]['soc'] += soc

        # ForwardTraversal(commits=self._commits,
        #                  op=op,
        #                  valid_cond=in_interval(begin, end))()

        for commit in self._commits:
            if begin > commit.creation_time:
                continue
            if end < commit.creation_time:
                break
            op(commit)

        return revisions

    def get_files_in_repository(self):
        return get_files_in_repository(root=self.root)

    def get_authors(self, filename: str, module_map=None):
        n_revs = 0
        authors = defaultdict(int)
        for commit in reversed(self._commits):
            for change in commit.changes:
                change_name = module_map(
                    change.filename) if module_map else change.filename
                if filename == change_name:
                    n_revs += 1
                    authors[commit.author] += 1
                    if change.old_filename:
                        filename = change.old_filename
        for author in authors:
            authors[author] = authors[author] / n_revs
        return authors

    def get_main_authors(self,
                         filename: str,
                         max_authors: int = 3,
                         module_map=None):
        authors = self.get_authors(filename=filename, module_map=module_map)
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

        # is_valid = in_interval(begin=begin, end=end)
        # for commit in self.commits:
        #     if is_valid(commit):
        #         op(commit)
        BackwardTraversal(commits=self._commits,
                          op=op,
                          valid_cond=in_interval(begin=begin, end=end))()
        return commits

    def get_commits(self, begin: datetime, end: datetime) -> List[Commit]:
        print(f'get commits in {begin} {end}')
        commits = [
            commit for commit in self.commits
            if in_interval(begin, end)(commit)
        ]
        # commits = []

        # def op(commit):
        #     commits.append(commit)

        # BackwardTraversal(commits=self._commits,
        #                   op=op,
        #                   valid_cond=in_interval(begin=begin, end=end))()
        # print(f'found {len(commits)} commits')
        return list(reversed(commits))

    def get_commits_after(self, sha: str):
        commits = []

    def calculate_complexity_over_range(self, filename: str, begin: datetime,
                                        end: datetime):
        commits = self.get_commits_for_file(filename=filename,
                                            begin=begin,
                                            end=end)
        print(f'trend commits')
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

    def add_complexity_analysis(self, end: str, stats):
        os.system(
            f'cd {self.root} && git checkout `git rev-list -n 1 --before={end} master`'
        )
        try:
            for filename in stats.keys():
                with open(self.root + filename, "r") as file_to_calc:
                    complexity_by_line = complexity_calculations.calculate_complexity_in(
                        file_to_calc.read())
                    d_stats = DescriptiveStats(filename, complexity_by_line)
                    if not stats[filename]:
                        print(f'MISSING: {filename}')
                    stats[filename]['lines'] = d_stats.n_revs
                    stats[filename]['complexity'] = d_stats.total
                    stats[filename]['mean_complexity'] = round(
                        d_stats.mean(), 2)
                    stats[filename]['complexity_sd'] = round(d_stats.sd(), 2)
                    stats[filename]['complexity_max'] = round(
                        d_stats.max_value(), 2)
        except Exception as exc:
            print(f'Exc: {type(exc)}:{exc}')
        os.system(f'cd {self.root} && git checkout master')
        return stats

    def add_proximity_analysis(self, begin: datetime, end: datetime, stats):
        proximities = self.get_proximities(begin=begin, end=end)
        # print(f'PRXI {proximities}')
        for proximity in proximities:
            filename = proximity[0]
            if not filename in stats:
                continue
            stats[filename]['proximity'] = proximity[2]
            stats[filename]['mean_proximity'] = proximity[3]
            stats[filename]['proximity_sd'] = proximity[4]
            stats[filename]['proximity_max'] = proximity[5]

    def read_proximities_from(self, begin: datetime, end: datetime):
        commits = self.get_commits(begin=begin, end=end)
        print(f'commits {len(commits)}')
        proximities = defaultdict(list)
        print(f'proximities {len(proximities)}')
        for idx in range(len(commits) - 1):
            current_commit = commits[idx]
            for change in current_commit.changes:
                if change.old_filename and change.old_filename in proximities:
                    proximities[change.filename] = proximities.pop(
                        change.old_filename)
            next_commit = commits[idx + 1]
            git_diff = read_diff_for(self.root, current_commit.sha,
                                     next_commit.sha)
            changes = parse_changes_per_file_in(git_diff)
            new_proximities = calc_proximity(changes)
            for name, proximity in new_proximities.items():
                proximities[name].append(proximity)

        return proximities

    def get_proximities(self, begin: datetime, end: datetime):
        proximities = self.read_proximities_from(begin=begin, end=end)
        stats = dict_as_stats(proximities)
        presentation_order = sorted(stats, key=lambda p: p.total, reverse=True)
        return [[
            p.name, p.n_revs + 1, p.total,
            round(p.mean(), 2),
            round(p.sd(), 2),
            p.max_value()
        ] for p in presentation_order]