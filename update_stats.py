from collections import defaultdict
from git_log import BackwardTraversal, ForwardTraversal, in_interval
from typing import List
from git_data import Commit
from copy import deepcopy


def compute_stats(commits: List[Commit], get_loc, get_complexity,
                  get_proximity):
    stats = defaultdict(lambda: defaultdict(dict))

    previous_sha = None

    def op(commit: Commit):
        nonlocal previous_sha
        for change in commit.changes:
            if change.old_filename and change.old_filename in stats:
                if change.old_filename not in stats:
                    print(f'{commit.sha} {change}')
                    print(f'kezs {stats.keys()}')
                stats[change.filename] = deepcopy(stats[change.old_filename])
            # if change.filename == 'Examples/FEniCS/PDE/Nonlinear_Heat_Transfer_PenaltyBC/CMakeLists.txt':
            #     print(f'sha: {commit.sha}')
            #     print(f'removed: {change.removed}')
            if change.removed:
                continue
            lines, complexity = get_complexity(filename=change.filename,
                                               sha=commit.sha)
            loc = get_loc(filename=change.filename, sha=commit.sha)
            proximity = get_proximity(filename=change.filename,
                                      sha=commit.sha,
                                      previous_sha=previous_sha)
            stats[change.filename][commit.sha] = {
                'name': change.filename,
                'loc': loc,
                'lines': lines,
                'soc': len(commit.changes),
                'complexity': complexity,
                'proximity': proximity
            }
        previous_sha = commit.sha

    for commit in commits:
        op(commit)


#    ForwardTraversal(commits=commits, op=op)()

    return stats


def compute_new_stats(db, git_log):
    last_sha = db.get_last_sha()
    new_commits = git_log.get_commits_after(last_sha)
    return compute_stats(new_commits)
