# from dataclasses import dataclass, field
from bokeh.plotting import figure
from bokeh.models import ColumnDataSource, HoverTool, Text
import circlify as circ
from color_map import get_colors

SCALE = 1

# @dataclass
# class Circle:
#     x: float = 0
#     y: float = 0
#     r: float = 0
#     level: int = 0
#     ex = field(default_factory=lambda: dict())

# def arrange_in_unit_circle(size_idx_pairs):
#     size_idx_pairs = sorted(size_idx_pairs, key=lambda x: x[0], reverse=True)
#     total = sum(size for size, _ in size_idx_pairs)
#     for size, __ in size_idx_pairs:
#         ratio = 0.8*size/total

# def mcirclify(layer, start_circle = Circle):
#     for entry in layer:
#         continue


def get_default_label(count, circle):
    """Generates a default label."""
    if circle.ex and "id" in circle.ex:
        label = str(circle.ex["id"])
    elif circle.ex and "datum" in circle.ex:
        label = circle.ex["datum"]
    elif circle.ex:
        label = str(circle.ex)
    else:
        label = ""
    return label


def in_circle(p, circle):
    return (p[0] - circle.x)**2 + (p[1] - circle.y)**2 <= circle.r**2


def get_name(circle):
    return get_default_label(0, circle)


def is_file(circle):
    return circle.ex and 'children' not in circle.ex


def get_full_name(a_circle, circles):
    if a_circle.level <= 1:
        return get_name(a_circle)
    parent = next(circle for circle in circles
                  if circle.level == a_circle.level -
                  1 and in_circle((a_circle.x, a_circle.y), circle))
    return get_full_name(parent, circles) + '/' + get_name(a_circle)


def get_main_author(module, stats):
    if module not in stats:
        return ''
    if 'authors' not in stats[module]:
        return ''
    main_author = ''
    max_revs = 0
    for author in stats[module]['authors'][0]:
        revs = stats[module]['authors'][0][author]
        if revs > max_revs:
            max_revs = revs
            main_author = author
    return main_author


class CircularPackage:
    def __init__(self, data, color_data, stats, width: int, height: int,
                 selected_callback) -> None:
        self._data = data
        self._color_data = color_data
        self._stats = stats
        self._selected_callback = selected_callback
        self.source = ColumnDataSource(
            data=dict(x=[], y=[], color=[], radius=[], name=[], level=[]))
        self.source.selected.on_change('indices', self.update_selected)  # pylint: disable=no-member
        self.selected = []
        self.full_names = []
        self.current_idx = None
        self.current_level = 0
        self.zoom_level = 0
        self.max_level = 0
        self.text_source = ColumnDataSource(
            data=dict(x=[], y=[], color=[], text=[]))
        self.circles = circ.circlify(self._data, show_enclosure=True)
        for circle in self.circles:
            circle.circle = circ._Circle(x=circle.circle.x,
                                         y=0.93 * circle.circle.y,
                                         r=circle.circle.r)
        self.plot = figure(x_range=(-1, 1),
                           y_range=(-1, 1),
                           plot_width=width,
                           plot_height=width,
                           tools='pan,reset,hover,tap,wheel_zoom',
                           tooltips=[
                               ('Name', '@name'),
                           ],
                           match_aspect=True)
        self.plot.toolbar.logo = None
        self.plot.toolbar_location = None
        self.plot.xaxis.visible = None
        self.plot.yaxis.visible = None
        self.plot.xgrid.grid_line_color = None
        self.plot.ygrid.grid_line_color = None
        self.plot.outline_line_alpha = 0

        self.plot.circle(x=0,
                         y=0,
                         radius=1,
                         color='white',
                         line_color='gray',
                         line_alpha=0.7,
                         alpha=0.1,
                         selection_fill_alpha=0.1,
                         nonselection_fill_alpha=0.1,
                         selection_line_alpha=0.1,
                         nonselection_line_alpha=0.1)

        self.plot.circle(source=self.source,
                         x='x',
                         y='y',
                         radius='radius',
                         color='color',
                         line_color='gray',
                         line_alpha=0.7,
                         alpha='alpha',
                         selection_fill_alpha='alpha',
                         nonselection_fill_alpha='alpha',
                         selection_line_alpha='alpha',
                         nonselection_line_alpha='alpha',
                         name="circles")
        hover_tool = self.plot.select(type=HoverTool)
        hover_tool.names = ["circles"]
        glyph = Text(x="x", y="y", text="text", text_color="white")
        self.plot.add_glyph(self.text_source, glyph)
        self.update_package(self._color_data, self._stats)

    def reset_selection(self):
        self.current_level = 0
        self.zoom_level = 0
        self.plot.x_range.update(start=-1, end=1)
        self.plot.y_range.update(start=-1, end=1)
        self.update_text_source()
        self._selected_callback()

    def update_selected(self, attr, old, new):
        self.selected = new
        if not self.selected:
            self.reset_selection()
            return

        new_level = max(self.source.data['level'][idx]
                        for idx in self.selected)
        self.current_level = new_level
        self.zoom_level = self.current_level

        try:
            self.current_idx = next(
                idx for idx in self.selected
                if self.source.data['level'][idx] == self.current_level)
        except StopIteration:
            self.current_idx = None
            self.reset_selection()
        else:
            x = self.source.data['x'][self.current_idx]
            y = self.source.data['y'][self.current_idx]
            r = self.source.data['radius'][self.current_idx]
            is_file = self.source.data['is_file'][self.current_idx]
            if is_file:
                self.zoom_level = self.current_level - 1
                zoom_idx = next(
                    idx for idx in self.selected
                    if self.source.data['level'][idx] == self.zoom_level)
                x = self.source.data['x'][zoom_idx]
                y = self.source.data['y'][zoom_idx]
                r = self.source.data['radius'][zoom_idx]

            self.plot.x_range.update(start=x - r, end=x + r)
            self.plot.y_range.update(start=y - r, end=y + r)
            self._selected_callback()

        self.update_package(self._color_data, self._stats)

    def update_text_source(self):
        reference_level = min(self.zoom_level + 1, self.max_level)
        self.text_source.data = dict(
            x=[circle.circle.x for circle in self.circles if circle.level > 0],
            y=[circle.circle.y for circle in self.circles if circle.level > 0],
            text=[
                get_name(circle) if circle.level == reference_level else ''
                for circle in self.circles if circle.level > 0
            ])

    def update_package(self, color_data, stats):
        self.max_level = max(self.circles, key=lambda x: x.level).level
        self._color_data = color_data
        self.full_names = [
            get_full_name(circle, self.circles) for circle in self.circles
            if circle.level > 0
        ]
        self._stats = stats
        author_list = [
            get_main_author(get_full_name(circle, self.circles),
                            stats=self._stats) for circle in self.circles
            if circle.level > 0
        ]
        color_weights = [
            self._color_data.get(name) or None for name in self.full_names
        ]
        colors = get_colors(color_weights)
        alphas = [0.1 if color == 'white' else 0.8 for color in colors]
        self.source.data = dict(
            x=[circle.circle.x for circle in self.circles if circle.level > 0],
            y=[circle.circle.y for circle in self.circles if circle.level > 0],
            radius=[
                circle.circle.r for circle in self.circles if circle.level > 0
            ],
            name=[
                get_name(circle) for circle in self.circles if circle.level > 0
            ],
            is_file=[
                is_file(circle) for circle in self.circles if circle.level > 0
            ],
            author=author_list,
            level=[
                circle.level for circle in self.circles if circle.level > 0
            ],
            color=colors,
            alpha=alphas)
        self.update_text_source()