from pytest import approx

from stats import compute_complexity, compute_proximities, read_locs


def test_compute_complexity():
    with open('tests/data/HilbertSpaceNorm.h', 'r') as code:
        lines, stats = compute_complexity(code.read())
        assert lines == 13
        assert stats['total'] == 11
        assert stats['mean'] == 11 / 13
        assert stats['sd'] == approx(0.77, rel=1e-2)
        assert stats['max'] == 2


def test_read_locs():
    with open('tests/data/cloc.csv') as cloc:
        locs = read_locs(cloc.read())
        assert 'HilbertSpaceNorm.h' in locs.keys()
        assert locs['HilbertSpaceNorm.h'] == 13


def test_compute_proximity():
    with open('tests/data/git_diff') as diff:
        proximities = compute_proximities(diff.read())
        assert proximities[
            'Spacy/Algorithm/CompositeStep/AffineCovariantSolver.cpp'] == 607
        assert proximities[
            'Spacy/Algorithm/CompositeStep/AffineCovariantSolver.h'] == 52
