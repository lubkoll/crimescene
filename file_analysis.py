from git_log import GitLog, DATE_FORMAT

import math
from datetime import datetime

from bokeh.core.enums import Align
from bokeh.layouts import column, row
from bokeh.models import ColumnDataSource, Div, Select
from bokeh.plotting import figure

COMPLEXITY_MEASURES = [
    'lines', 'complexity', 'mean_complexity', 'complexity_sd', 'churn'
]
COMPLEXITY_X = ['revisions', 'date']


class FileAnalysis:
    def __init__(self, git_log: GitLog, selected_file: str, begin: datetime,
                 end: datetime, width: int, height: int) -> None:
        self._git_log = git_log
        self._begin = begin
        self._end = end
        self._width = width
        self._height = height
        self._selected_file = selected_file
        self._complexity_trend = []
        self.complexity_analysis_source = ColumnDataSource(
            data=dict(x=[], y=[], sha=[]))

        self.complexity_x = Select(title='Complexity X',
                                   value=COMPLEXITY_X[0],
                                   options=COMPLEXITY_X)
        self.complexity_x.on_change('value', self.update_detailed_analysis)

        self.complexity_measures = Select(title='Complexity Measure',
                                          value=COMPLEXITY_MEASURES[2],
                                          options=COMPLEXITY_MEASURES)
        self.complexity_measures.on_change('value',
                                           self.update_detailed_analysis)
        self.layout = column(
            row(self.complexity_measures,
                self.complexity_x,
                align=Align.center),  # pylint: disable=no-member
            self.create_complexity_trend(),
            self.create_coupling_table())

    def set_selected_file(self, selected_file: str, begin: datetime,
                          end: datetime):
        self._selected_file = selected_file
        self._begin = begin
        self._end = end
        self.update_complexity_trend()

    def update_complexity_trend(self):
        self._complexity_trend = self._git_log.compute_complexity_trend(
            filename=self._selected_file, begin=self._begin, end=self._end)

    def update_detailed_analysis(self, attr, old, new):
        if len(self.layout.children) < 3:  # pylint: disable=unsubscriptable-object
            return
        self.layout.children[1] = self.create_complexity_trend()  # pylint: disable=unsubscriptable-object

    def create_coupling_table(self):
        coupling_table = ['Coupling: </br>']
        if self._selected_file:
            data, n_revisions = self._git_log.get_couplings(
                filename=self._selected_file, begin=self._begin, end=self._end)
            coupled = sorted(data.items(), key=lambda x: x[1], reverse=True)
            # coupled = []
            # for name, n_coupled in data.items():
            #     if name == 'count':
            #         continue
            #     if n_coupled > 2 and n_coupled / n_revisions > 0.2:
            #         coupled.append((name, n_coupled))
            # coupled = sorted(coupled, key=lambda x: x[1], reverse=True)
            # for name, n_coupled in coupled:
            #     coupling_table.append(f'{name}: {n_coupled}/{n_revisions}')
            for name, n_coupled in coupled:
                coupling_table.append(f'{name}: {n_coupled}/{n_revisions}')
        return Div(text='</br>'.join(coupling_table),
                   width=self._width,
                   height=self._height)

    def get_churn_for_file(self, filename, t, key):
        idx = 1 if key == 'added_lines' else 2
        return sum([
            churn[idx] for churn in self._git_log.get_churn_for(
                filename=filename, begin=self._begin, end=self._end) if t ==
            self._git_log.get_commit_from_sha(churn[0]).creation_time.date()
        ])

    def create_complexity_trend(self):
        kw = dict(title=f'Complexity Trend: {self._selected_file}',
                  tooltips=[
                      ('sha', '@sha'),
                      ('msg', '@commit_msg'),
                      ('date', '@date'),
                      ('author', '@author'),
                      ('complexity', '@complexity'),
                      ('mean_complexity', '@mean_complexity'),
                      ('complexity_sd', '@complexity_sd'),
                      ('added_lines', '@added_lines'),
                      ('removed_lines', '@removed_lines'),
                  ],
                  x_axis_label=self.complexity_x.value,
                  y_axis_label=self.complexity_measures.value,
                  x_axis_type='linear' if self.complexity_x.value
                  == COMPLEXITY_X[0] else 'datetime')

        p = figure(plot_height=600,
                   plot_width=800,
                   tools='pan,xwheel_zoom,hover,reset',
                   **kw)
        p.toolbar.logo = None
        x = []
        x0 = []
        churn = []
        measure = []
        if self.complexity_measures.value == 'churn':
            churn = self._git_log.get_churn_for(filename=self._selected_file,
                                                begin=self._begin,
                                                end=self._end)
            revs = [sha for sha, _, _ in churn]
            measure = [0 for _ in revs]
            if self.complexity_x.value == COMPLEXITY_X[0]:
                x = list(range(len(revs)))
                p.xaxis.ticker = x
                p.xaxis.major_label_overrides = dict(enumerate(revs))
                p.xaxis.major_label_orientation = math.pi / 4
            else:
                x = [
                    self._git_log.get_commit_from_sha(
                        sha).creation_time.timestamp() for sha, _, _ in churn
                ]
            x0 = [
                self._git_log.get_commit_from_sha(sha).creation_time
                for sha, _, _ in churn
            ]
        else:
            measure = [
                row[1 +
                    COMPLEXITY_MEASURES.index(self.complexity_measures.value)]
                for row in self._complexity_trend
            ]
            revs = [row[0] for row in self._complexity_trend]
            x0 = [
                self._git_log.get_commit_from_sha(row[0]).creation_time
                for row in self._complexity_trend
            ]
            if self.complexity_x.value == COMPLEXITY_X[0]:
                x = list(range(len(revs)))
                p.xaxis.ticker = x
                p.xaxis.major_label_overrides = dict(enumerate(revs))
                p.xaxis.major_label_orientation = math.pi / 4
            else:
                x = [
                    self._git_log.get_commit_from_sha(
                        row[0]).creation_time.timestamp()
                    for row in self._complexity_trend
                ]

        added = [
            self.get_churn_for_file(filename=self._selected_file,
                                    t=t.date(),
                                    key='added_lines') for t in x0
        ]
        removed = [
            self.get_churn_for_file(filename=self._selected_file,
                                    t=t.date(),
                                    key='removed_lines') for t in x0
        ]
        msgs = [
            self._git_log.get_commit_from_sha(sha).msg for sha, _, _ in churn
        ] if self.complexity_measures.value == 'churn' else [
            self._git_log.get_commit_from_sha(row[0]).msg
            for row in self._complexity_trend
        ]
        authors = [
            self._git_log.get_commit_from_sha(sha).author
            for sha, _, _ in churn
        ] if self.complexity_measures.value == 'churn' else [
            self._git_log.get_commit_from_sha(row[0]).author
            for row in self._complexity_trend
        ]
        self.complexity_analysis_source.data = dict(
            x=x,
            y=measure,
            sha=revs,
            commit_msg=msgs,
            author=authors,
            date=[
                self._git_log.get_commit_from_sha(
                    row[0]).creation_time.strftime(DATE_FORMAT)
                for row in self._complexity_trend
            ],
            complexity=[
                row[1 + COMPLEXITY_MEASURES.index('complexity')]
                for row in self._complexity_trend
            ],
            mean_complexity=[
                row[1 + COMPLEXITY_MEASURES.index('mean_complexity')]
                for row in self._complexity_trend
            ],
            complexity_sd=[
                row[1 + COMPLEXITY_MEASURES.index('complexity_sd')]
                for row in self._complexity_trend
            ],
            added_lines=added,
            removed_lines=removed)

        if self.complexity_measures.value == 'churn':
            p.line(x='x',
                   y='removed_lines',
                   source=self.complexity_analysis_source,
                   line_width=3,
                   line_color='blue')
            p.circle(x='x',
                     y='removed_lines',
                     source=self.complexity_analysis_source,
                     color='blue',
                     size=10)
            p.line(x='x',
                   y='added_lines',
                   source=self.complexity_analysis_source,
                   line_width=3,
                   line_color='orange')
            p.circle(x='x',
                     y='added_lines',
                     source=self.complexity_analysis_source,
                     color='orange',
                     size=10)
        else:
            p.line(x='x',
                   y='y',
                   source=self.complexity_analysis_source,
                   line_width=3,
                   line_color='orange')
            p.circle(x='x',
                     y='y',
                     source=self.complexity_analysis_source,
                     color='orange',
                     size=10)
        return p

    def get_plot(self):
        self.layout = column(
            row(self.complexity_measures,
                self.complexity_x,
                align=Align.center),  # pylint: disable=no-member
            self.create_complexity_trend(),
            self.create_coupling_table())
        return self.layout
