from git_data import get_commit_list
from update_stats import compute_stats


def get_complexity(filename: str, sha: str):
    return 23, {'total': 10, 'mean': 1.3, 'sd': 0.3, 'max': 3}


def test_compute_stats():
    with open('tests/data/spacy.log', 'r') as git_log:
        commits = get_commit_list(git_log.read())
        stats = compute_stats(commits,
                              get_loc=lambda filename, sha: 166,
                              get_complexity=get_complexity)
        assert stats['LICENSE']['b3d38b33']['loc'] == 166
        assert stats['LICENSE']['b3d38b33']['name'] == 'LICENSE'
        assert stats['LICENSE']['b3d38b33']['lines'] == 23
        assert stats['LICENSE']['b3d38b33']['complexity']['total'] == 10
        assert stats['LICENSE']['b3d38b33']['complexity']['mean'] == 1.3
        assert stats['LICENSE']['b3d38b33']['complexity']['sd'] == 0.3
        assert stats['LICENSE']['b3d38b33']['complexity']['max'] == 3
