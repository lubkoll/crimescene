import argparse
from collections import defaultdict
from git_log import get_full_log, get_log_after_revision
import os
from update_stats import compute_new_stats, compute_stats
from git_data import get_commit_list
import stats_cache
from stats import get_loc_in_revision, get_complexity, get_proximities_for_file

CACHENAME = 'cache.json'
COMMITSNAME = 'commits.json'

# def compute_stats(commits: List[Commit], get_loc, get_complexity):


def parse_args():
    parser = argparse.ArgumentParser(description='update cache')
    parser.add_argument('--root', help='repo root dir')

    return parser.parse_args()


if __name__ == "__main__":
    print('start cache update')
    args = parse_args()
    stats = defaultdict(dict)
    commits = []
    if os.path.isfile(COMMITSNAME):
        commits = stats_cache.load_commits()

    if os.path.isfile(CACHENAME):
        print('load cache update')
        stats = stats_cache.load_stats()

    print('get last sha')
    last_sha = stats.get('last_sha')
    last_sha = '9f7ebce4'

    print('get git log')
    git_log = get_log_after_revision(
        root=args.root, sha=last_sha) if last_sha else get_full_log(
            root=args.root)
    print('get commits')
    new_commits = get_commit_list(git_log=git_log)
    commits.extend(new_commits)
    print(f'COMMITS: {len(commits)}')
    stats_cache.store_commits(commits=commits)

    def get_loc(filename: str, sha: str):
        return 0
        # return get_loc_in_revision(root=args.root, filename=filename, sha=sha)

    def _get_complexity(filename: str, sha: str):
        return get_complexity(root=args.root, filename=filename, sha=sha)

    def _get_proximity(filename: str, sha: str, previous_sha):
        if previous_sha is None:
            return 0
        return get_proximities_for_file(root=args.root,
                                        filename=filename,
                                        sha=sha,
                                        previous_sha=previous_sha)

    print('compute cache update')
    new_stats = compute_stats(commits=new_commits,
                              get_loc=get_loc,
                              get_complexity=_get_complexity,
                              get_proximity=_get_proximity)
    if 'Spacy/Spaces/RealSpace.h' in new_stats:
        print('FOUND2')
    for filename, data in new_stats.items():
        stats[filename].update(data)
    print('store cache update')
    stats_cache.store_stats(stats)
