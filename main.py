from git_log import GitLog
import json
import os
import sqlite3
import sys
import time

from miner.git_complexity_trend import compute_complexity_trend
sys.path.append(os.path.dirname(os.path.realpath(__file__)))
from datetime import datetime, timedelta, timezone

from bokeh.core.enums import Align
from bokeh.layouts import column, row
from bokeh.models import ColumnDataSource, Select, Div, DateRangeSlider, Button
from bokeh.plotting import curdoc, figure
from pathlib import Path
from wordcloud import WordCloud, STOPWORDS

import transform.csv_as_enclosure_json as csv_as_enclosure_json
from analyze_git_log import add_complexity_analysis, to_days
from circular_package import CircularPackage, get_main_author
from color_map import get_colors
from process_git_log import get_loc, add_loc, read_locs

HOME = str(Path.home())
PROJECT = 'Spacy'
PROJECT_STOPWORDS = set()
STATS_PATH = f'{HOME}/.stats/{PROJECT}'
PREFIX = f'/home/lars/projects/{PROJECT}/'
CONTROL_WIDTH = 420
PLOT_WIDTH = 1200
PLOT_HEIGHT = 900
WORDCLOUD_IDX = 2
COMPLEXITY_TREND_IDX = 1
COLUMNS = [
    'revisions', 'loc', 'complexity', 'mean_complexity', 'complexity_max',
    'complexity_sd', 'soc', 'churn'
]
COMPLEXITY_MEASURES = [
    'lines', 'complexity', 'mean_complexity', 'complexity_sd', 'churn'
]
COMPLEXITY_X = ['revisions', 'date']
CIRC_PACK_CRITERIA = [
    'soc', 'mean_complexity', 'complexity', 'complexity_sd', 'revisions',
    'author', 'age', 'churn'
]
DATE_FORMAT = '%Y-%m-%d'

DB_PATH = "cache.db"


class SQL:
    def __init__(self, path=DB_PATH) -> None:
        self._path = path
        self._connection = None
        self._cursor = None
        self.create_table()

    def _connect(self):
        self._connection = sqlite3.connect(DB_PATH)
        self._cursor = self._connection.cursor()

    def _disconnect(self):
        self._connection.commit()
        self._connection.close()
        self._connection = None
        self._cursor = None

    def create_table(self):
        self._connect()
        self._cursor.execute(
            'CREATE TABLE IF NOT EXISTS projects(project TEXT)')
        self._disconnect()

    def add_project(self, project_name: str):
        self._connect()
        self._cursor.execute(
            f'CREATE TABLE IF NOT EXISTS {project_name}(start INTEGER NOT NULL, end INTEGER NOT NULL, stats JSON NOT NULL, couplings JSON NOT NULL)'
        )
        is_present = self._cursor.execute(
            f'SELECT project FROM projects WHERE project = ?',
            (project_name, )).fetchone()
        print(f'is {project_name} present: {is_present is not None}')
        if not is_present:
            print(f'Add {project_name}')
            self._cursor.execute('INSERT INTO projects(project) VALUES (?)',
                                 (project_name, ))
        self._disconnect()

    def store_stats(self, project_name: str, start: int, end: int, stats,
                    couplings):
        self._connect()
        is_present = self._cursor.execute(
            f'SELECT start, end FROM {project_name} WHERE start = ? AND end = ?',
            (start, end)).fetchone()
        if is_present:
            print(
                f'{project_name}:{start}-{end} already present. Skipping insert.'
            )
            return

        cmd = f'INSERT INTO {project_name}(start, end, stats, couplings) VALUES(?,?,?,?)'
        self._cursor.execute(
            cmd, (start, end, json.dumps(stats), json.dumps(couplings)))
        self._disconnect()

    def read_stats(self, project_name: str):
        self._connect()
        stat_rows = self._cursor.execute(
            f'SELECT start, end, stats, couplings FROM {project_name}'
        ).fetchall()
        stats = {tuple(row[0:2]): json.loads(row[2]) for row in stat_rows}
        couplings = {tuple(row[0:2]): json.loads(row[3]) for row in stat_rows}
        self._disconnect()
        return stats, couplings


def wordcloud_file(end: str, period: timedelta):
    return f'{STATS_PATH}/wordcloud_{end}_{to_days(period)}.png'


def generate_wordcloud(git_log: GitLog, end: datetime, period: timedelta):
    text = ' '.join(git_log.commit_msg(begin=end - period,
                                       end=end)).replace("'", "")
    wordcloud = WordCloud(stopwords=STOPWORDS | PROJECT_STOPWORDS,
                          background_color='white')
    wordcloud.generate(text)
    wordcloud.to_file(
        wordcloud_file(end=end.strftime(DATE_FORMAT), period=period))


def get_workcloud_plot(end: datetime, period: timedelta):
    wordcloud = figure(x_range=(0, 1),
                       y_range=(0, 1),
                       plot_width=PLOT_WIDTH,
                       plot_height=250,
                       tools='')
    wordcloud.toolbar.logo = None
    wordcloud.toolbar_location = None
    wordcloud.xaxis.visible = None
    wordcloud.yaxis.visible = None
    wordcloud.xgrid.grid_line_color = None
    wordcloud.ygrid.grid_line_color = None
    wordcloud.outline_line_alpha = 0
    wordcloud.image_url(url=[
        f'crimescene/static/wordcloud_{end.strftime(DATE_FORMAT)}_{to_days(period)}.png'
    ],
                        x=0,
                        y=1)
    return wordcloud


def get_age(stats, inverse=False):
    def f(value):
        return 1 / value if inverse else value

    return {
        name: f(
            to_days(
                datetime.now(tz=timezone.utc) - datetime.fromtimestamp(
                    stats[name]['last_change'], tz=timezone.utc)))
        for name in stats
    }


def ms_to_datetime(ms: float):
    return datetime.fromtimestamp(ms / 1000, tz=timezone.utc)


class App:
    def __init__(self) -> None:
        self.git_log = GitLog.from_dir(PREFIX)
        self.selected = []
        self.complexity_trend = []
        self.db = SQL()
        self.db.add_project(project_name=PROJECT)
        stats, couplings = self.db.read_stats(project_name=PROJECT)
        self.stats = stats
        self.couplings = couplings
        self.start_loc = 0
        self.summary = Div(text='', width=CONTROL_WIDTH, height=100)

        today = datetime.now(tz=timezone.utc)
        period_start = today - timedelta(days=800)

        self.source = ColumnDataSource(
            data=dict(x=[], y=[], module=[], revisions=[], size=[]))
        self.source.selected.on_change('indices', self.update_selected)  # pylint: disable=no-member
        self.complexity_analysis_source = ColumnDataSource(
            data=dict(x=[], y=[], sha=[]))
        self.x_menu = Select(title='X-Axis', value=COLUMNS[3], options=COLUMNS)
        self.x_menu.on_change('value', self.update_table)

        self.y_menu = Select(title='Y-Axis', value=COLUMNS[0], options=COLUMNS)
        self.y_menu.on_change('value', self.update_table)

        self.color = Select(title='Color', value=COLUMNS[6], options=COLUMNS)
        self.color.on_change('value', self.update_table)

        self.circ_pack_color = Select(title='Overview Color',
                                      value=CIRC_PACK_CRITERIA[1],
                                      options=CIRC_PACK_CRITERIA)
        self.circ_pack_color.on_change('value', self.update_circ_pack_color)

        self.complexity_x = Select(title='Complexity X',
                                   value=COMPLEXITY_X[0],
                                   options=COMPLEXITY_X)
        self.complexity_x.on_change('value', self.update_detailed_analysis)

        self.complexity_measures = Select(title='Complexity Measure',
                                          value=COMPLEXITY_MEASURES[2],
                                          options=COMPLEXITY_MEASURES)
        self.complexity_measures.on_change('value',
                                           self.update_detailed_analysis)

        self.range_slider = DateRangeSlider(
            start=self.git_log.first_commit_date(),
            end=today,
            step=1,
            value=(period_start, today),
            title='Range',
            width=CONTROL_WIDTH + PLOT_WIDTH - 100)

        self.range_button = Button(label="Select",
                                   button_type="default",
                                   width=50)
        self.range_button.on_click(self.update_date_range)

        self.plus_button = Button(label='+', button_type='default', width=50)
        self.plus_button.on_click(self.increase_dates)
        self.minus_button = Button(label='-', button_type='default', width=50)
        self.minus_button.on_click(self.decrease_dates)

        generate_wordcloud(git_log=self.git_log,
                           end=self.date_slider_value(),
                           period=self.period_length())
        wordcloud = get_workcloud_plot(end=self.date_slider_value(),
                                       period=self.period_length())
        self.update_stats(period_start=period_start, period_end=today)
        self.update_source()
        self.circular_package = self.get_circular_package()
        controls = column(row(self.minus_button, self.plus_button),
                          self.summary,
                          wordcloud,
                          self.x_menu,
                          self.y_menu,
                          self.color,
                          self.circ_pack_color,
                          width=CONTROL_WIDTH)
        self.layout = column(
            row(self.range_slider, self.range_button),
            row(
                controls,
                column(self.create_figure(), self.circular_package.plot,
                       self.create_churn_plot())),
        )
        self.update_wordcloud()
        self.update_summary()

    def increase_dates(self):
        start, end = self.range_slider.value
        start = ms_to_datetime(start)
        end = ms_to_datetime(end)
        dt = end - start
        new_end = end + dt
        if new_end > ms_to_datetime(self.range_slider.end):
            new_end = ms_to_datetime(self.range_slider.end)
            dt = new_end - end
        start += dt
        end = new_end
        self.range_slider.value = (1000 * start.timestamp(),
                                   1000 * end.timestamp())
        self.update_date_range()

    def decrease_dates(self):
        start, end = self.range_slider.value
        start = ms_to_datetime(start)
        end = ms_to_datetime(end)
        dt = end - start
        new_start = start - dt
        if new_start < ms_to_datetime(self.range_slider.start):
            new_start = ms_to_datetime(self.range_slider.start)
            dt = start - new_start
        start = new_start
        end -= dt
        self.range_slider.value = (1000 * start.timestamp(),
                                   1000 * end.timestamp())
        self.update_date_range()

    def get_stats(self):
        return self.stats[self.range_slider.value]

    def get_couplings(self, module):
        return self.couplings[self.range_slider.value][module]

    def get_circ_color_data(self, value):
        if value == 'soc' and self.selected:

            selected_file = self.get_selected_file()

            def get_value(name):
                couplings = self.get_couplings(selected_file)
                return 2 + 2 * couplings[
                    name] if name in couplings else 1 if name == selected_file else 0

            return {module: get_value(module) for module in self.get_stats()}

        if value == 'author':
            main_authors = {
                module: get_main_author(module, self.get_stats())
                for module in self.get_stats()
            }
            indexed_main_authors = list(
                set(
                    get_main_author(module, self.get_stats())
                    for module in self.get_stats()))
            print(f'INDEXED {indexed_main_authors}')
            print(f'MA {main_authors}')

            return {
                module: 3 * indexed_main_authors.index(main_authors[module])
                for module in self.get_stats()
            }

        if value == 'age':
            return get_age(self.get_stats(), inverse=True)

        if value == 'churn':
            return {
                name: sum(churn['added_lines'] + churn['removed_lines']
                          for churn in data['churn'])
                for name, data in self.get_stats().items()
            }

        return {
            module: data[value]
            for module, data in self.get_stats().items()
        }

    def update_circ_pack_color(self, attr, old, new):
        self.circular_package.update_package(self.get_circ_color_data(new),
                                             stats=self.get_stats())

    def get_circular_package(self):
        circ_data = translate_dict(csv_as_enclosure_json.run(
            self.get_stats()))['children']
        return CircularPackage(data=circ_data,
                               width=PLOT_HEIGHT,
                               height=PLOT_HEIGHT,
                               color_data=self.get_circ_color_data(
                                   self.circ_pack_color.value),
                               stats=self.get_stats(),
                               selected_callback=self.update_circ_selected)

    def add_repo_main_authors(self, max_authors: int = 3):
        for module, data in self.get_stats().items():
            data['authors'] = self.git_log.get_main_authors(
                filename=module, max_authors=max_authors)

    def date_slider_value(self):
        return ms_to_datetime(self.range_slider.value[1])

    def period_length(self):
        return ms_to_datetime(self.range_slider.value[1]) - ms_to_datetime(
            self.range_slider.value[0])

    def update_summary(self):
        n_changed = len([
            name for name, data in self.get_stats().items()
            if data['revisions'] > 0
        ])
        n_authors = len(
            set(author for authors in self.get_stats().values()
                for author in authors))
        self.summary.text = f'Summary:</br>#files: {len(self.get_stats())}</br>#changed: {n_changed}</br>#authors: {n_authors}'

    def update_stats(self, period_start: datetime, period_end: datetime):
        if self.range_slider.value in self.stats:
            self.update_summary()
            self.start_loc = sum(
                read_locs(
                    get_loc(
                        root=PREFIX,
                        before=period_start.strftime(DATE_FORMAT))).values())
            return
        t0 = time.time()
        t1 = time.time()
        stats, couplings = self.git_log.get_revisions(begin=period_start,
                                                      end=period_end)
        self.start_loc = sum(
            read_locs(
                get_loc(root=PREFIX,
                        before=period_start.strftime(DATE_FORMAT))).values())
        print(f'START LOC {self.start_loc}')
        t2 = time.time()
        self.stats[self.range_slider.value] = stats
        self.couplings[self.range_slider.value] = couplings
        t3 = time.time()
        locs = get_loc(root=PREFIX, before=period_end.strftime(DATE_FORMAT))
        add_loc(self.get_stats(), locs)
        t4 = time.time()
        add_complexity_analysis(root=PREFIX,
                                end=period_end.strftime(DATE_FORMAT),
                                stats=self.get_stats())

        t5 = time.time()
        self.add_repo_main_authors()
        t6 = time.time()
        self.update_summary()
        t7 = time.time()
        print(f'{t1-t0}, {t2-t1}, {t3-t2}, {t4-t3}, {t5-t4}, {t6-t5}, {t7-t6}')
        self.db.store_stats(project_name=PROJECT,
                            start=self.range_slider.value[0],
                            end=self.range_slider.value[1],
                            stats=stats,
                            couplings=couplings)

    def update_wordcloud(self):
        generate_wordcloud(git_log=self.git_log,
                           end=self.date_slider_value(),
                           period=self.period_length())
        wordcloud = get_workcloud_plot(end=self.date_slider_value(),
                                       period=self.period_length())
        self.layout.children[1].children[0].children[WORDCLOUD_IDX] = wordcloud  # pylint: disable=unsupported-assignment-operation,unsubscriptable-object

    def get_period_as_datetime(self):
        period_start, period_end = self.range_slider.value
        return ms_to_datetime(period_start), ms_to_datetime(period_end)

    def update_date_range(self):
        self.circular_package.reset_selection()
        period_start, period_end = self.get_period_as_datetime()
        self.update_stats(period_start=period_start, period_end=period_end)
        self.update_source()
        self.update_wordcloud()
        self.circular_package = self.get_circular_package()
        self.layout.children[1].children[1].children[0] = self.create_figure()  # pylint: disable=unsupported-assignment-operation,unsubscriptable-object
        self.layout.children[1].children[1].children[  # pylint: disable=unsupported-assignment-operation,unsubscriptable-object
            1] = self.circular_package.plot
        self.layout.children[1].children[1].children[  # pylint: disable=unsupported-assignment-operation,unsubscriptable-object
            2] = self.create_churn_plot()

    def update_source(self):
        churn = [
            sum(churn['added_lines'] + churn['removed_lines']
                for churn in data['churn'])
            for data in self.get_stats().values()
        ]
        color_data = churn if self.color.value == 'churn' else [
            data[self.color.value] for data in self.get_stats().values()
        ]

        def get_author(author, ratio):
            return f'{author} ({round(ratio,2)})'

        self.source.data = dict(
            module=list(self.get_stats().keys()),
            loc=[data['loc'] for data in self.get_stats().values()],
            revisions=[
                data['revisions'] for data in self.get_stats().values()
            ],
            size=[
                9 + 0.2 * float(data['loc'])
                for data in self.get_stats().values()
            ],
            lines=[data['lines'] for data in self.get_stats().values()],
            complexity=[
                data['complexity'] for data in self.get_stats().values()
            ],
            mean_complexity=[
                data['mean_complexity'] for data in self.get_stats().values()
            ],
            complexity_sd=[
                data['complexity_sd'] for data in self.get_stats().values()
            ],
            complexity_max=[
                data['complexity_max'] for data in self.get_stats().values()
            ],
            soc=[data['soc'] for data in self.get_stats().values()],
            color=get_colors(color_data),
            authors=[
                ', '.join(
                    get_author(author, ratio) for author, ratio in
                    self.get_stats()[name]['authors'][0].items())
                for name in self.get_stats()
            ],
            n_authors=[
                self.get_stats()[name]['authors'][1]
                for name in self.get_stats()
            ],
            age=list(get_age(self.get_stats()).values()),
            churn_overview=[
                f"{sum(churn['added_lines'] + churn['removed_lines'] for churn in data['churn'])}:{sum(churn['added_lines'] for churn in data['churn'])}:{sum(churn['removed_lines'] for churn in data['churn'])}"
                for data in self.get_stats().values()
            ],
            churn=churn)

    def get_churn(self, t, key):
        return sum(churn[key] for data in self.get_stats().values()
                   for churn in data['churn']
                   if t == datetime.fromtimestamp(churn['timestamp'],
                                                  tz=timezone.utc).date())

    def get_churn_for_file(self, filename, t, key):
        idx = 3 if key == 'added_lines' else 4
        period_start, period_end = self.get_period_as_datetime()
        return sum([
            churn[idx] for churn in self.git_log.get_churn_for(
                filename=filename, begin=period_start, end=period_end)
            if t == churn[1].date()
        ])

    def get_time_axis(self):
        start_date = ms_to_datetime(self.range_slider.value[0])
        end_date = self.date_slider_value()
        n_days = int(to_days(end_date - start_date))
        return [start_date + timedelta(days=t) for t in range(1, n_days + 1)]

    def create_churn_plot(self):
        p = figure(title="Churn",
                   x_axis_label='days',
                   y_axis_label='loc',
                   x_axis_type='datetime',
                   plot_width=PLOT_WIDTH,
                   plot_height=PLOT_HEIGHT,
                   tools='pan,xwheel_zoom,reset')
        x = self.get_time_axis()
        added = [self.get_churn(t.date(), key='added_lines') for t in x]
        removed = [self.get_churn(t.date(), key='removed_lines') for t in x]
        locs = [self.start_loc]
        for idx in range(len(x) - 1):
            locs.append(locs[idx] + added[idx] - removed[idx])
        p.line(x=x, y=added, color='orange', legend_label='added')
        p.line(x=x, y=removed, color='blue', legend_label='removed')
        p.line(x=x, y=locs, color='gray', legend_label='lines of code')
        p.legend.location = "top_left"
        return p

    def create_figure(self):
        self.update_source()
        x_title = self.x_menu.value
        y_title = self.y_menu.value

        kw = dict(
            title="",
            tooltips=[('Module', '@module'), ('LOC', '@loc'),
                      ('#rev', '@revisions'), ('lines', '@lines'),
                      ('complexity', '@complexity'),
                      ('mean_complexity', '@mean_complexity'),
                      ('complexity_sd', '@complexity_sd'),
                      ('complexity_max', '@complexity_max'), ('SOC', '@soc'),
                      ('authors', '@authors'), ('#authors', '@n_authors'),
                      ('age', '@age'), ('churn', '@churn_overview')],
            x_axis_label=x_title,
            y_axis_label=y_title,
            y_axis_type='log' if y_title == 'revisions' else 'linear',
        )
        p = figure(plot_width=PLOT_WIDTH,
                   plot_height=PLOT_HEIGHT,
                   tools='pan,wheel_zoom,hover,reset,tap',
                   **kw)
        p.toolbar.logo = None
        if y_title == 'revisions':
            p.y_range.start = 0.8

        p.circle(x=x_title,
                 y=y_title,
                 source=self.source,
                 color='color',
                 size='size',
                 line_color="white",
                 alpha=0.6,
                 hover_color='white',
                 hover_alpha=0.5)
        return p

    def get_selected_file(self):
        return self.source.data['module'][self.selected[0]]

    def update_complexity_trend(self):
        selected_file = self.get_selected_file()
        self.complexity_trend = compute_complexity_trend(
            PREFIX, selected_file,
            (self.git_log.first_commit_sha(), self.git_log.last_commit_sha()))

    def display_complexity_trend(self):
        selected_file = self.get_selected_file()
        kw = dict(
            title=f'Complexity Trend: {selected_file}',
            tooltips=[
                ('sha', '@sha'),
                ('msg', '@commit_msg'),
                ('date', '@date'),
                #   ('complexity', '@complexity'),
                #   ('mean_complexity', '@mean_complexity'),
                #   ('complexity_sd', '@complexity_sd'),
                #   ('added_lines', '@added_lines'),
                #   ('removed_lines', '@removed_lines'),
            ],
            x_axis_label=self.complexity_x.value,
            y_axis_label=self.complexity_measures.value,
            x_axis_type='linear'
            if self.complexity_x.value == COMPLEXITY_X[0] else 'datetime')

        p = figure(plot_height=600,
                   plot_width=800,
                   tools='pan,box_zoom,hover,reset',
                   **kw)
        p.toolbar.logo = None
        x = []
        x0 = []
        churn = []
        measure = []
        if self.complexity_measures.value == 'churn':
            period_start, period_end = self.get_period_as_datetime()
            churn = self.git_log.get_churn_for(filename=selected_file,
                                               begin=period_start,
                                               end=period_end)
            revs = [sha for sha, _, _, _, _ in churn]
            measure = [0 for _ in revs]
            if self.complexity_x.value == COMPLEXITY_X[0]:
                x = list(range(len(revs)))
                p.xaxis.ticker = x
                p.xaxis.major_label_overrides = dict(enumerate(revs))
            else:
                x = [time for _, time, _, _, _ in churn]
            x0 = [time for _, time, _, _, _ in churn]
        else:
            measure = [
                row[1 +
                    COMPLEXITY_MEASURES.index(self.complexity_measures.value)]
                for row in self.complexity_trend
            ]
            revs = [row[0] for row in self.complexity_trend]
            x0 = [
                datetime.fromtimestamp(int(row[5]))
                for row in self.complexity_trend
            ]
            if self.complexity_x.value == COMPLEXITY_X[0]:
                x = list(range(len(revs)))
                p.xaxis.ticker = x
                p.xaxis.major_label_overrides = dict(enumerate(revs))
            else:
                x = [
                    datetime.fromtimestamp(int(row[5]))
                    for row in self.complexity_trend
                ]

        added = []
        for t in x0:
            # if 'linearBlockOperator' in selected_file:
            #     print(f'{t}:')
            added.append(
                self.get_churn_for_file(filename=selected_file,
                                        t=t.date(),
                                        key='added_lines'))
        #     self.get_churn_for_file(filename=selected_file,
        #                             t=t.date(),
        #                             key='added_lines') for t in x0
        # ]
        removed = [
            self.get_churn_for_file(filename=selected_file,
                                    t=t.date(),
                                    key='removed_lines') for t in x0
        ]
        msgs = [msg for _, _, msg, _, _ in churn
                ] if self.complexity_measures.value == 'churn' else [
                    row[6] for row in self.complexity_trend
                ]
        print(f'MSGS {msgs}')
        self.complexity_analysis_source.data = dict(
            x=x,
            y=measure,
            sha=revs,
            commit_msg=msgs,
            # date=[
            #     datetime.fromtimestamp(int(row[5]),
            #                            tz=timezone.utc).strftime(DATE_FORMAT)
            #     for row in self.complexity_trend
            # ],
            # complexity=[
            #     row[1 + COMPLEXITY_MEASURES.index('complexity')]
            #     for row in self.complexity_trend
            # ],
            # mean_complexity=[
            #     row[1 + COMPLEXITY_MEASURES.index('mean_complexity')]
            #     for row in self.complexity_trend
            # ],
            # complexity_sd=[
            #     row[1 + COMPLEXITY_MEASURES.index('complexity_sd')]
            #     for row in self.complexity_trend
            # ],
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

    def create_complexity_trend(self):
        self.update_complexity_trend()
        return self.display_complexity_trend()

    def create_coupling_table(self):
        coupling_table = ['Coupling: </br>']
        reference = self.get_selected_file()
        data = self.get_couplings(reference)
        n_revisions = data['count']
        coupled = []
        for name, n_coupled in data.items():
            if name == 'count':
                continue
            if n_coupled > 2 and n_coupled / n_revisions > 0.2:
                coupled.append((name, n_coupled))
        coupled = sorted(coupled, key=lambda x: x[1], reverse=True)
        for name, n_coupled in coupled:
            coupling_table.append(f'{name}: {n_coupled}/{n_revisions}')
        return Div(text='</br>'.join(coupling_table),
                   width=2 * CONTROL_WIDTH,
                   height=CONTROL_WIDTH)

    def update_table(self, attr, old, new):
        self.layout.children[1].children[1].children[0] = self.create_figure()  # pylint: disable=unsupported-assignment-operation,unsubscriptable-object

    def update_circ_selected(self):
        if not self.circular_package.current_idx:
            self.source.selected.indices = []
            return
        name = self.circular_package.full_names[
            self.circular_package.current_idx]
        try:
            idx = self.source.data['module'].index(name)
        except ValueError:
            self.source.selected.indices = []
        else:
            self.source.selected.indices = [idx]

    def update_selected(self, attr, old, new):
        self.selected = new
        if len(self.layout.children[1].children) == 3:  # pylint: disable=unsubscriptable-object
            if self.selected:
                self.layout.children[1].children[2].children[  # pylint: disable=unsupported-assignment-operation,unsubscriptable-object
                    COMPLEXITY_TREND_IDX] = self.create_complexity_trend()
                self.layout.children[1].children[2].children[  # pylint: disable=unsupported-assignment-operation,unsubscriptable-object
                    COMPLEXITY_TREND_IDX + 1] = self.create_coupling_table()
            else:
                del self.layout.children[1].children[2]  # pylint: disable=unsupported-delete-operation,unsubscriptable-object
        if len(self.layout.children[1].children) == 2 and self.selected:  # pylint: disable=unsubscriptable-object
            self.layout.children[1].children.append(  # pylint: disable=no-member,unsubscriptable-object
                column(
                    row(self.complexity_measures,
                        self.complexity_x,
                        align=Align.center),  # pylint: disable=no-member
                    self.create_complexity_trend(),
                    self.create_coupling_table()))
        if self.circ_pack_color.value == 'soc':
            self.update_circ_pack_color('value', '',
                                        self.circ_pack_color.value)

    def update_detailed_analysis(self, attr, old, new):
        if len(self.layout.children[1].children) < 3:  # pylint: disable=unsubscriptable-object
            return
        self.layout.children[1].children[2].children[  # pylint: disable=unsubscriptable-object
            COMPLEXITY_TREND_IDX] = self.display_complexity_trend()


MIN_DATUM = 0.0


def translate_dict(d):
    new_d = {
        'id': d['name'],
    }
    if 'children' in d and d['children']:
        new_d['children'] = [translate_dict(c) for c in d['children']]
    if d.get('size') is not None:
        new_d['datum'] = max(float(d.get('size')), 1e-3)
    else:
        new_d['datum'] = sum(child['datum'] for child in new_d['children'])
    new_d['datum'] = max(new_d['datum'], MIN_DATUM)
    return new_d


app = App()
curdoc().add_root(app.layout)
curdoc().title = "Crime Scene"
