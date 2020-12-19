from git_data import get_commit_list


def test_get_commit_list():
    with open('tests/data/spacy.log') as git_log:
        commits = get_commit_list(git_log.read())
        assert commits[0].sha == 'b3d38b33'
        assert commits[-1].sha == '1cb97ce8'
        assert commits[0].author == 'Lars Lubkoll'
        assert commits[-1].author == 'Lars Lubkoll'