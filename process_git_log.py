from collections import defaultdict
import time
import re
import subprocess


def _run_cmd(root, args):
    return subprocess.Popen(args, stdout=subprocess.PIPE,
                            cwd=root).communicate()[0].decode("utf-8")


def _read_revisions_matching(root, git_arguments):
    git_log = _run_cmd(root, git_arguments)
    revs = []
    # match a line like: d804759 Documented tree map visualizations
    # ignore everything except the commit number:
    rev_expr = re.compile(r'([^\s]+)')
    for line in git_log.split("\n"):
        m = rev_expr.search(line)
        if m:
            revs.append(m.group(1))
    return revs[::-1]


def read_revs(root: str, rev_start, rev_end):
    """ Returns a list of all commits in the given range.
	"""
    rev_range = rev_start + '..' + rev_end
    return _read_revisions_matching(
        root, git_arguments=['git', 'log', rev_range, '--oneline'])


def read_diff_for(root, rev1, rev2):
    return _run_cmd(root, ['git', 'diff', rev1, rev2])


def read_diff_for_file(root: str, filename: str, rev1: str, rev2: str):
    return _run_cmd(root, ['git', 'diff', rev1, rev2, '--', filename])


# if __name__ == "__main__":
#     start = time.time()
#     root = '/home/lars/projects/Spacy'
#     git_log = get_log(root=root, after='2018-09-01', before='2019-01-01')
#     get_authors(root=root, filename='CMakeLists.txt')
