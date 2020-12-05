import subprocess
import re


def _as_rev_range(start, end):
    return start + '..' + end


def _run_git_cmd(root, git_arguments):
    return subprocess.Popen(git_arguments, stdout=subprocess.PIPE,
                            cwd=root).communicate()[0].decode("utf-8")


def _read_revisions_matching(root, git_arguments):
    git_log = _run_git_cmd(root, git_arguments)
    revs = []
    # match a line like: d804759 Documented tree map visualizations
    # ignore everything except the commit number:
    #rev_expr = re.compile(r'([^\s]+)')
    for line in git_log.split("\n"):
        tokens = line[1:-1].split()
        if tokens:
            revs.append((tokens[0], tokens[1], ' '.join(tokens[3:])))
    #   m = rev_expr.search(line)
    #  if m:
    #     revs.append(m.group(1))
    return revs[::-1]


def _git_cmd_for(rev_start, rev_end):
    rev_range = rev_start + '..' + rev_end
    return ['git', 'log', rev_range, "--format='%h %cd %s'", '--date=raw']


#    return ['git', 'log', rev_range, '--oneline']


def read_revs(root, rev_start, rev_end):
    """ Returns a list of all commits in the given range.
    """
    return _read_revisions_matching(root,
                                    git_arguments=_git_cmd_for(
                                        rev_start, rev_end))


def read_revs_for(root: str, file_name, rev_start, rev_end):
    return _read_revisions_matching(
        root, git_arguments=_git_cmd_for(rev_start, rev_end) + [file_name])


def read_diff_for(rev1, rev2):
    return _run_git_cmd(['git', 'diff', rev1, rev2])


def read_file_diff_for(root, file_name, rev1, rev2):
    return _run_git_cmd(root, ['git', 'diff', rev1, rev2, file_name])


def read_version_matching(root, file_name, rev):
    return _run_git_cmd(root, ['git', 'show', rev + ':' + file_name])


def read_commit_messages(root, start: str, end: str):
    return _run_git_cmd(root, [
        'git', 'log', "--pretty=format:'%s'", f'--after={start}',
        f'--before={end}'
    ]).replace('\n', ' ').replace("'", "")
