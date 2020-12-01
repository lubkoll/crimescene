from bokeh.palettes import RdYlGn11

COLORS = RdYlGn11
N_COLORS = len(COLORS)


def get_colors(color_data):
    min_color_data = min(datum for datum in color_data if datum is not None)
    max_color_data = max(datum for datum in color_data if datum is not None)
    dsoc = (max_color_data - min_color_data) / N_COLORS
    color_idx_map = {(min_color_data + i * dsoc,
                      min_color_data + (i + 1) * dsoc): i
                     for i in range(N_COLORS)}

    def get_color(value):
        if value is None:
            return "white"
        for range, idx in color_idx_map.items():
            if range[0] <= value <= range[1]:
                return COLORS[idx]

    return [get_color(data) for data in color_data]