from get_wordcloud import get_new_workcloud_plot
from git_log import GitLog, DATE_FORMAT
from file_analysis import FileAnalysis
from get_db import SQL
import os
import sys
import time

sys.path.append(os.path.dirname(os.path.realpath(__file__)))
from datetime import datetime, timedelta, timezone

from bokeh.layouts import column, row
from bokeh.models import ColumnDataSource, Select, Div, DateRangeSlider, Button
from bokeh.plotting import curdoc, figure
from pathlib import Path

import transform.csv_as_enclosure_json as csv_as_enclosure_json
from analyze_git_log import add_complexity_analysis, to_days
from circular_package import CircularPackage, get_main_author
from color_map import get_colors
from process_git_log import get_loc, add_loc, read_locs

HOME = str(Path.home())
PROJECT = 'Spacy'
STATS_PATH = f'{HOME}/.stats/{PROJECT}'
PREFIX = f'/home/lars/projects/{PROJECT}/'
CONTROL_WIDTH = 420
PLOT_WIDTH = 1200
PLOT_HEIGHT = 900
WORDCLOUD_IDX = 2
COLUMNS = [
    'revisions', 'loc', 'complexity', 'mean_complexity', 'complexity_max',
    'complexity_sd', 'soc', 'churn'
]
CIRC_PACK_CRITERIA = [
    'soc', 'mean_complexity', 'complexity', 'complexity_sd', 'revisions',
    'author', 'age', 'churn'
]


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
        self.db = SQL()
        self.db.add_project(project_name=PROJECT)
        stats = self.db.read_stats(project_name=PROJECT)
        self.stats = stats
        self.start_loc = 0
        self.summary = Div(text='', width=CONTROL_WIDTH, height=100)

        today = datetime.now(tz=timezone.utc)
        period_start = today - timedelta(days=800)
        self.file_analysis = FileAnalysis(git_log=self.git_log,
                                          selected_file='',
                                          begin=period_start,
                                          end=today,
                                          width=2 * CONTROL_WIDTH,
                                          height=CONTROL_WIDTH)

        self.source = ColumnDataSource(
            data=dict(x=[], y=[], module=[], revisions=[], size=[]))
        self.source.selected.on_change('indices', self.update_selected)  # pylint: disable=no-member
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

        wordcloud = get_new_workcloud_plot(git_log=self.git_log,
                                           end=self.date_slider_value(),
                                           period=self.period_length(),
                                           width=PLOT_WIDTH)
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

    def get_circ_color_data(self, value):
        if value == 'soc' and self.selected:

            selected_file = self.get_selected_file()
            begin, end = self.get_period_as_datetime()
            couplings, _ = self.git_log.get_couplings(filename=selected_file,
                                                      begin=begin,
                                                      end=end)

            def get_value(name):
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
        stats, _ = self.git_log.get_revisions(begin=period_start,
                                              end=period_end)
        self.start_loc = sum(
            read_locs(
                get_loc(root=PREFIX,
                        before=period_start.strftime(DATE_FORMAT))).values())
        print(f'START LOC {self.start_loc}')
        t2 = time.time()
        self.stats[self.range_slider.value] = stats
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
                            stats=stats)

    def update_wordcloud(self):
        wordcloud = get_new_workcloud_plot(git_log=self.git_log,
                                           end=self.date_slider_value(),
                                           period=self.period_length(),
                                           width=PLOT_WIDTH)
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
        if self.selected:
            begin, end = self.get_period_as_datetime()
            self.file_analysis.set_selected_file(
                selected_file=self.get_selected_file(), begin=begin, end=end)
        if len(self.layout.children[1].children) == 3:  # pylint: disable=unsubscriptable-object
            if self.selected:
                self.layout.children[1].children[  # pylint: disable=unsubscriptable-object
                    2] = self.file_analysis.get_plot()
            else:
                del self.layout.children[1].children[2]  # pylint: disable=unsupported-delete-operation,unsubscriptable-object
        if len(self.layout.children[1].children) == 2 and self.selected:  # pylint: disable=unsubscriptable-object
            self.layout.children[1].children.append(  # pylint: disable=no-member,unsubscriptable-object
                self.file_analysis.get_plot())
        if self.circ_pack_color.value == 'soc':
            self.update_circ_pack_color('value', '',
                                        self.circ_pack_color.value)


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
