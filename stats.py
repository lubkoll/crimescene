from git_proximity_analysis import parse_changes_per_file_in
from process_git_log import read_diff_for, read_diff_for_file
from desc_stats import as_stats
from typing import Optional, Tuple
from git_log import _run_cmd, calc_proximity
import miner.complexity_calculations as complexity_calculations

from git_data import Change, Commit


def read_locs(locs_str):
    lines = locs_str.split('\n')
    locs = {}
    for line in lines:
        if not line:
            continue

        entries = line.split(',')
        name = entries[1]
        if name == 'filename':
            continue
        name = name[2:]
        try:
            locs[name] = int(entries[4])
        except ValueError:
            print(f'E {entries[4]}')
    return locs


def get_loc(root: str, filename: str) -> int:
    return read_locs(
        _run_cmd(root=root,
                 args=['cloc', filename, '--csv', '--unix',
                       '--quiet']))[filename]


def get_loc_in_revision(root: str, filename: str, sha: str) -> int:
    _run_cmd(root=root, args=['git', 'checkout', sha])
    locs = read_locs(
        _run_cmd(root=root,
                 args=['cloc', filename, '--csv', '--unix',
                       '--quiet'])).get(filename)
    _run_cmd(root=root, args=['git', 'checkout', 'master'])
    return locs if locs else 0


def compute_complexity(historic_version: str):
    complexity_by_line = complexity_calculations.calculate_complexity_in(
        historic_version)
    stats = as_stats('', complexity_by_line)
    return stats.n_revs, {
        'total': stats.total,
        'mean': stats.mean(),
        'sd': stats.sd(),
        'max': stats.max_value()
    }


def get_complexity(root: str, filename: str, sha: str) -> Tuple[int, dict]:
    historic_version = _run_cmd(root, ['git', 'show', sha + ':' + filename])
    return compute_complexity(historic_version=historic_version)


def compute_proximities(git_diff: str):
    changes = parse_changes_per_file_in(git_diff)
    return calc_proximity(changes)


def get_proximities(root: str, sha: str, previous_sha: str) -> dict:
    git_diff = read_diff_for(root, sha, previous_sha)
    return compute_proximities(git_diff)


def get_proximities_for_file(root: str, filename: str, sha: str,
                             previous_sha: str) -> dict:
    git_diff = read_diff_for_file(root=root,
                                  filename=filename,
                                  rev1=sha,
                                  rev2=previous_sha)
    return compute_proximities(git_diff).get(filename, 0)


def get_stats_for_file_in_commit(root: str,
                                 commit: Commit,
                                 change: Change,
                                 previous_sha: Optional[str] = None):
    _run_cmd(root=root, args=['git', 'checkout', commit.sha])
    proximities = get_proximities(root=root,
                                  sha=commit.sha,
                                  previous_sha=previous_sha)
    filename = change.filename
    lines, complexity = get_complexity(root=root,
                                       filename=filename,
                                       sha=commit.sha)
    stats = {
        'loc': get_loc(root=root, filename=filename),
        'lines': {
            'total': lines,
            'added': change.added_lines,
            'removed': change.removed_lines
        },
        'complexity': complexity,
        'proximity': proximities[filename]
    }
    _run_cmd(root=root, args=['git', 'checkout', 'master'])
    return stats


def get_stats(root: str, commit: Commit, previous_sha: Optional[str] = None):
    return {
        change.filename:
        get_stats_for_file_in_commit(root=root,
                                     commit=commit,
                                     change=change,
                                     previous_sha=previous_sha)
        for change in commit.changes
    }
