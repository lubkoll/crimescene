from datetime import datetime, timedelta, timezone

from bokeh.core.enums import Align
from util import timer, to_days
from git_log import GitLog
from color_map import get_colors
from bokeh.plotting import figure
from bokeh.layouts import column, row
from bokeh.models import ColumnDataSource, Select

LONG_TERM_PLOT_CRITERIA = [
    'lines', 'complexity', 'mean complexity', 'complexity sd'
]


class LongTermPlot:
    def __init__(self, stats, git_log: GitLog, period_start: datetime,
                 period_end: datetime, width: int, height: int) -> None:
        self.git_log: GitLog = git_log
        self._period_start: datetime = period_start
        self._period_end: datetime = period_end
        self._width: int = width
        self._height: int = height
        self._stats = stats
        self.complexity_trend = {}
        self.churn = {'x': [], 'loc': [], 'added': [], 'removed': []}

        self.long_term_plot_menu = Select(title='Long Term Plot',
                                          value='churn',
                                          options=['churn', 'rising hotspot'])
        self.long_term_plot_menu.on_change('value', self.update_long_term_plot)
        self.long_term_plot_criterion = Select(
            title='Long Term Plot Criterion',
            value=LONG_TERM_PLOT_CRITERIA[0],
            options=LONG_TERM_PLOT_CRITERIA)
        self.long_term_plot_criterion.on_change(
            'value', self.update_long_term_criterion)
        self.source = ColumnDataSource(data=dict(t=[],
                                                 x0=[],
                                                 x1=[],
                                                 x2=[],
                                                 x3=[],
                                                 x4=[],
                                                 x5=[],
                                                 x6=[],
                                                 x7=[],
                                                 x8=[],
                                                 x9=[]))
        self.layout = column(
            row(self.long_term_plot_menu,
                self.long_term_plot_criterion,
                align=Align.center), figure())  # pylint: disable=no-member

    def compute_churn(self):
        x = self.get_time_axis()
        added = [self.get_churn(t.date(), key='added_lines') for t in x]
        removed = [self.get_churn(t.date(), key='removed_lines') for t in x]
        #            locs = [self.start_loc]
        locs = [0]
        for idx in range(len(x) - 1):
            locs.append(locs[idx] + added[idx] - removed[idx])

        self.churn = dict(x=x, added=added, removed=removed, loc=locs)

    def get_time_axis(self):
        n_days = int(to_days(self._period_end - self._period_start))
        return [
            self._period_start + timedelta(days=t)
            for t in range(1, n_days + 1)
        ]

    def get_churn(self, t, key):
        return sum(churn[key] for data in self._stats.values()
                   for churn in data['churn']
                   if t == datetime.fromtimestamp(churn['timestamp'],
                                                  tz=timezone.utc).date())

    def update_long_term_plot(self, attr, old, new):
        if old == 'churn' and new == 'rising hotspot':
            self.compute_complexity_trend()
        if old == 'rising hotspot' and new == 'churn':
            self.compute_churn()
        self.layout.children[1] = self.create_plot()  # pylint: disable=unsupported-assignment-operation,unsubscriptable-object

    def update_long_term_criterion(self, attr, old, new):
        self.update_long_term_plot(attr, new, old)
        # if self.is_churn_plot():
        #     return
        # self.update_source()

    def compute_complexity_trend(self):
        self.complexity_trend = {
            filename:
            self.git_log.compute_complexity_trend(filename=filename,
                                                  begin=self._period_start,
                                                  end=self._period_end)
            for filename in self._stats
        }

    @timer
    def update(self, stats, period_start: datetime, period_end: datetime):
        self._stats = stats
        self._period_start = period_start
        self._period_end = period_end
        if self.is_churn_plot():
            self.compute_churn()
        else:
            self.compute_complexity_trend()
        self.update_long_term_plot(None, None, None)

    def is_churn_plot(self):
        return self.long_term_plot_menu.value == 'churn'

    # def compute_rank_changes(self):

    def update_source(self):
        stats_idx = 2
        if self.long_term_plot_criterion.value == 'mean complexity':
            stats_idx = 3
        if self.long_term_plot_criterion.value == 'complexity sd':
            stats_idx = 4
        if self.long_term_plot_criterion.value == 'lines':
            stats_idx = 1
        initial_complexities = sorted(
            [(filename, data[0][stats_idx])
             for filename, data in self.complexity_trend.items() if data],
            key=lambda x: x[1],
            reverse=True)
        final_complexities = sorted(
            [(filename, data[-1][stats_idx])
             for filename, data in self.complexity_trend.items() if data],
            key=lambda x: x[1],
            reverse=True)

        c0 = {
            filename: idx
            for idx, (filename, _) in enumerate(initial_complexities)
        }
        c1 = {
            filename: idx
            for idx, (filename, _) in enumerate(final_complexities)
        }
        rank_changes = [(filename, c0[filename] - c1[filename])
                        for filename in c0]

        rank_changes.sort(key=lambda x: x[1], reverse=True)
        rank_changes = rank_changes[:10]
        color_data = get_colors([rank for _, rank in rank_changes])
        x = list(
            set(
                self.git_log.get_commit_from_sha(row[0]).creation_time
                for filename, _ in rank_changes
                for row in self.complexity_trend[filename]))
        x.sort()
        self.source.data = dict(t=[],
                                x0=[],
                                x1=[],
                                x2=[],
                                x3=[],
                                x4=[],
                                x5=[],
                                x6=[],
                                x7=[],
                                x8=[],
                                x9=[])

    def create_plot(self):
        if self.is_churn_plot():
            return self.create_churn_plot()
        return self.create_rising_hotspot_plot()

    @timer
    def create_churn_plot(self):
        p = figure(title=self.long_term_plot_menu.value,
                   x_axis_label='date',
                   y_axis_label='loc',
                   x_axis_type='datetime',
                   plot_width=self._width,
                   plot_height=self._height,
                   tools='pan,xwheel_zoom,reset')
        x = self.churn['x']
        p.line(x=x,
               y=self.churn['added'],
               color='orange',
               legend_label='added')
        p.line(x=x,
               y=self.churn['removed'],
               color='blue',
               legend_label='removed')
        p.line(x=x,
               y=self.churn['loc'],
               color='gray',
               legend_label='lines of code')
        p.legend.location = "top_left"
        p.legend.click_policy = "hide"
        return p

    @timer
    def create_rising_hotspot_plot(self):
        p = figure(title=self.long_term_plot_menu.value,
                   x_axis_label='date',
                   y_axis_label=self.long_term_plot_criterion.value,
                   x_axis_type='datetime',
                   plot_width=self._width,
                   plot_height=self._height,
                   tools='pan,xwheel_zoom,reset')
        stats_idx = 2
        if self.long_term_plot_criterion.value == 'mean complexity':
            stats_idx = 3
        if self.long_term_plot_criterion.value == 'complexity sd':
            stats_idx = 4
        if self.long_term_plot_criterion.value == 'lines':
            stats_idx = 1
        initial_complexities = sorted(
            [(filename, data[0][stats_idx])
             for filename, data in self.complexity_trend.items() if data],
            key=lambda x: x[1],
            reverse=True)
        final_complexities = sorted(
            [(filename, data[-1][stats_idx])
             for filename, data in self.complexity_trend.items() if data],
            key=lambda x: x[1],
            reverse=True)

        c0 = {
            filename: idx
            for idx, (filename, _) in enumerate(initial_complexities)
        }
        c1 = {
            filename: idx
            for idx, (filename, _) in enumerate(final_complexities)
        }
        rank_changes = [(filename, c0[filename] - c1[filename])
                        for filename in c0]

        rank_changes.sort(key=lambda x: x[1], reverse=True)
        rank_changes = rank_changes[:10]
        color_data = get_colors([rank for _, rank in rank_changes])
        x = list(
            set(
                self.git_log.get_commit_from_sha(row[0]).creation_time
                for filename, _ in rank_changes
                for row in self.complexity_trend[filename]))
        x.sort()
        for (filename, rank_change), color in zip(rank_changes, color_data):
            trend = self.complexity_trend[filename]
            previous = 0

            def get_value(t):
                nonlocal previous
                for row in trend:
                    if self.git_log.get_commit_from_sha(
                            row[0]).creation_time == t:
                        previous = row[stats_idx]
                        return row[stats_idx]
                return previous

            y = [get_value(t) for t in x]

            p.line(x=x,
                   y=y,
                   color=color,
                   legend_label=filename + ' ' + str(rank_change))

        p.legend.location = "top_left"
        p.legend.click_policy = "hide"
        return p