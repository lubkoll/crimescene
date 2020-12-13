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


def dict_as_stats(all_proximities):
    return [
        DescriptiveStats(name, proximities_for_one)
        for name, proximities_for_one in all_proximities.items()
    ]