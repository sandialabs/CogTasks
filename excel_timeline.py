from enum import Enum

import xlsxwriter
from math import floor

class FMT(Enum):
    '''
    Timeline formats - dicts specifying properties that can be passed to workbook.add_format
    to create an instance of xlswriter.format.Format in the workbook.
    '''
    default = {}
    bold = {'bold':True}
    good = {'font_color': '#006100', 'bg_color':'#c6efce', 'border': 1, 'center_across': True} # these colors are taken from the Excel 'Bad' format
    bad = {'font_color': '#9c0006', 'bg_color':'#ffc7ce', 'border': 1, 'center_across': True} # these colors are taken from the Excel 'Bad' format
    event = {'bg_color':'#ffe699'}
    rollup = {'bg_color':'#c5d9f1', 'center_across': True}
    rollup_background = {'bold':True, 'bg_color':'#dce6f1', 'border':1, 'border_color':'#d4d4d4'} # border_color copied from excel


class Event:
    '''
    Used to specify an entry on a row in a timeline, extending from a start time to an end time.
    '''

    def __init__(self, description, start, end, format=FMT.event):
        self.description = description
        self.start = start
        self.end = end
        self.format = format

    def __str__(self):
        return f'{self.start}:{self.end}:{self.description}'

class Row:
    '''
    Used to specify a single row on a timeline, and (recursively) any child_rows when may be indented underneath it.
    '''
    def __init__(self, label, events=None, collapsed=False, format=None):
        '''
        :param label: label for the row
        :param events: optional list of Event instances
        :param collapsed: if true, I am collapsed and all my child rows are hidden
        '''

        self.label = label
        ''' label of the row - will be showed in leftmost column of spreadsheet. '''

        self.events = list(events) if events else []
        for e in self.events:
            assert(isinstance(e, Event))
        ''' events on this row
            These are not (necessarily) stored in time order. 
        '''

        self.child_rows = Rows()
        ''' rows indented underneath this row, indexed by their label. 
            childrows contains direct children, i.e. their indentation is 1 greater than this row
            the child rows may have their own chid rows, recursively
        '''

        self.collapsed = collapsed
        ''' if true, any child rows will be hidden initially.  Irrelevant if no child rows. '''

        self.format = format
        ''' specifies the format of the row label (does not apply to events on this row) '''

    def add_child_row(self, row):
        self.child_rows.add_row(row)

    def add_event(self, event):
        self.events.append(event)

    def add_rollup_event(self, label, format=FMT.rollup):
        '''
        add an event to this row with the specified label and whose start and end times
          are the min/max of all children (recursively) in child rows.
        '''
        self.add_event(Event(label, self.event_min(0,include_children=True), self.event_max(0,include_children=True), format=format))

    def event_min(self, default=None, include_children=False):
        '''
        returns the start of the earliest in this row
        returns default if there are no events in the row
        '''
        a = [e.start for e in self.visit_events(include_children)]
        return min(a) if a else default

    def event_max(self, default=None, include_children=False):
        '''
        returns the end of the latest-to-end event in this row
        returns default if there are no events in the row
        '''
        a = [e.end for e in self.visit_events(include_children)]
        return max(a) if a else default

    def __str__(self):
        return '{}: {}'.format(self.label, ' '.join(str(e) for e in self.events))

    def sort_child_rows(self, key=lambda r: r.label):
        '''
        Sort the child rows of this row (if any) with the specified key,
          which defaults to sorting alphabetically by label
        '''
        self.child_rows.rows = sorted(self.child_rows.rows, key=key)

    def visit_events(self, include_children=False):
        '''
        yield each of the Events on this Row.
          If include_children is true, also visits the Events on child rows, recursively.
        '''
        for e in self.events:
            yield e
        if include_children:
            for r in self.child_rows.rows:
                yield from r.visit_events(include_children)

    def get_last_child_row(self, indent=1):
        '''
        visit all child rows in depth-first order and return the last-visited child at the specified indent level.
        e.g. indent=1 means the last element of self.child_rows.  indent=0 returns this row.
        Raises ValueError if there are no descendants at the specified level.
        '''
        result = None

        if indent == 0:
            result = self
        elif indent > 0:
            for i,r in self.child_rows.visit_rows(indent=1, min_indent=indent, max_indent=indent):
                result = r
        else:
            raise ValueError(f'Row.get_last_child_row: indent must be > 0, got {indent}')

        if result is None:
            raise ValueError(f'Row.get_last_child_row: row {self.label} has no children at indent level {indent}')

        return result

class Rows:
    '''
        a list of Row.
        It is legal for multiple rows to have the same label.
    '''

    def __init__(self):
        self.rows = []
        '''
        The list of rows.  not using a dict because multiple rows can have the same label.
        '''

    def add_row(self, row):
        '''
        append a row to the end of the list of rows.
        '''
        self.rows.append(row)

    def find_row(self, label_or_test, create=False):
        '''
        find the first row (in depth-first order) that matches label_or_test
        :param label_or_test: if a string, specifies a label; otherwise must be a callable that returns true for a match.
        '''

        for r in self.find_rows(label_or_test):
            return r

        if create:
            r = Row(label_or_test)
            self.add_row(r)
            return r

        raise ValueError('find_row: no match for {}'.format(label_or_test))

    def find_row_path(self, path, create=False):
        '''
        Search for an ancestry of rows matching 'path'
        If none exists, create if create is true, else raise ValueError
        '''
        rows = self
        row = None
        for p in path: # walk down the path
            row = rows.find_row(p, create)
            rows = row.child_rows
        return row

    def find_rows(self, label_or_test):
        '''
        iterate rows (in depth-first order) that match label_or_test
        :param label_or_test: if a string, specifies a label; otherwise must be a callable that returns true for a matching row instance.
        '''
        if isinstance(label_or_test, str):
            for indent, row in self.visit_rows():
                if row.label == label_or_test:
                    yield row
        else:
            for indent, row in self.visit_rows():
                if label_or_test(row):
                    yield row

    def visit_rows(self, indent=0, min_indent=None, max_indent=None):
        '''
        iterate the rows and their children recursively in depth-first order.

        :param indent: the starting depth (normally 0)
        :param min_indent: do not visit rows whose depth is less than this
        :param max_indent: do not visit rows whose depth is greater than this
        :return:
        '''

        for row in self.rows:
            if (min_indent is None or indent >= min_indent) and (max_indent is None or indent <= max_indent):
                yield indent, row
            yield from row.child_rows.visit_rows(indent + 1, min_indent, max_indent)

    def print(self):
        for indent, row in self.visit_rows():
            print("{}{}".format(' '*indent, row))

def hrs_mins(t):
    ''' format time, in seconds, in a short format, e.g. -3720 is -1:02 '''
    sign = "-" if t < 0 else ""
    t = int(abs(t)) # whole seconds
    hrs = int(t/3600)
    mins = int((t-hrs*3600)/60)
    return "{}{}:{:02d}".format(sign, hrs, mins)


def hrs_mins_sec(t):
    ''' format time, in seconds, in a short format, e.g. -3722 is -1:02:02 '''
    return "{}:{:02d}".format(hrs_mins(t), int(abs(t)%60))

def round_down(mod, x):
    y = int(floor(x / mod) * mod)
    #print("round_down({}, {})={}".format(mod,x,y))
    return y


def deconflict(events):
    '''
    yield a sequence of events that is modified if necessary so they don't overlap,
    giving precedence to events that start later.  This means earlier events may be 'clobbered' and not in the result at all.
    '''

    events = sorted(events, key = lambda e: e.start)

    for e1, e2 in zip(events, events[1:]):
        end_by = e2.start-1
        if e1.end <= end_by:
            yield e1 # no need to chop it off
        elif e1.start <= end_by:
            e11 = Event(e1.description, e1.start, end_by) # return new event which is a copy but ends sooner
            yield e11
        else:
            pass # don't return e1 at all because it's clobbered by subsequent events.

    # the last one is not enumerated by the list above because it has no successor, and cannot be pre-empted.
    if events:
        yield events[-1]

def write_excel_timeline(filename, rows, mins_per_col=1, worksheet_name=None, title=None):
    workbook = xlsxwriter.Workbook(filename)

    worksheet = workbook.add_worksheet(worksheet_name)
    worksheet.outline_settings(symbols_below=0)

    # timestep is the number of seconds between time axis labels
    if mins_per_col == 1:
        timestep = 5 * 60
    elif mins_per_col == 10:
        timestep = 60 * 60
    else:
        raise ValueError("mins_per_col must be 1 or 10")

    try:
        start_time = round_down(timestep, min([ev.start for indent, row in rows.visit_rows() for ev in row.events]))
    except ValueError:
        start_time = 0

    try:
        end_time = max([ev.end for indent, row in rows.visit_rows() for ev in row.events])
    except ValueError:
        end_time = 100

    def get_format(format):
        '''
        :param format: a dict of properties, see https://xlsxwriter.readthedocs.io/format.html
        :return: the corresponding xlswriter.format.Format, added to the workbook if needed.
        '''

        if not hasattr(workbook, '_timeline_formats'):
            workbook._timeline_formats = {}

        if isinstance(format, FMT):
            format = format.value

        key = tuple(sorted(format.items()))
        if key not in workbook._timeline_formats:
            f = workbook.add_format(format)
            workbook._timeline_formats[key] = f

        return workbook._timeline_formats[key]

    def start_col(event_time):
        ''' map specified event start time in seconds to the corresponding column index '''
        return 1 + int((event_time - start_time) / (60 * mins_per_col))

    def colspan(t0, t1):
        '''
        map a specified event start and end times to the beginning / ending column indices.
            There is no standalone 'end_col' function because you need the start col to compute the end col.
        '''
        col0 = start_col(t0)

        # subtract 1 from the end column; otherwise subsequent events usually overlap.
        # the problem is that often an event ends and the next one starts soon after (the same or next second), so rounding makes the previous end and next start the same number.
        # so subtracting 1 is (usually) equivalent to depicting the event starting at the start of its first partial minute, and ending at the start of its last partial minute
        c1 = max(col0, start_col(t1) - 1)

        return (col0, c1)

    row = 0 # index of current row for output.  This is used by many of the functions below, but modified
        # only in the body of this function near the end.


    def write_cols(col1, col2, label, format=None, comment=None, merge=False, border=False, indent=None):
        '''
        A low-level function that is used to output timeline events, or row labels, etc. on the current row.

        merge: if true, allow the cells from col1 to col2 to be merged into a single cell (if col1 != col2)
          This has an unexpected consequence however - the label cannot overflow out of a merged cell, even
          if the following cell is empty.  This is bad in the gantt chart because there are a lot of short-duration events
          with whitespace after.

        fill cells corresponding to the specified columns with the given label.
        Note: the reason for not specifying the default format by default is because this presumably explicitly records
          that each individual cell should use the default format, which is very redundant.
        '''
        assert col2 >= col1

        if col1 != col2 and merge:
            worksheet.merge_range(row, col1, row, col2, label)
            if comment:
                worksheet.write_comment(row, col1, comment)
        else:
            for col in range(col1, col2 + 1):
                if border:
                    if isinstance(format, FMT):
                        format = format.value
                    if not isinstance(format, dict):
                        raise ValueError("format must be specified to write_cols as a dict for borders to be added but got: {}".format(format))
                    f = dict(format) # make a copy before modifying
                    f['bottom'] = True
                    f['top'] = True
                    f['left'] = True if col == col1 else False
                    f['right'] = True if col == col2 else False
                    format = f

                if indent:
                    if format is None:
                        format = {}
                    assert isinstance(format, dict), "format must be specified to write_cols as a dict for indentation to be added."
                    f = dict(format) # make a copy before modifying
                    f['indent'] = indent
                    format = f

                if format:
                    worksheet.write(row, col, label if col == col1 else None, get_format(format))
                else:
                    worksheet.write(row, col, label if col == col1 else None)

                if comment and col == col2:
                    worksheet.write_comment(row, col, comment, {'y_scale': 2, 'x_scale': 2})

    def write_event(event):
        comment = event.description + '\n'
        if event.start == event.end:
            comment += "Time: {}".format(hrs_mins_sec(event.start))
        else:
            comment += "Start: {}\nEnd: {}\nDuration: {}".format(hrs_mins_sec(event.start), hrs_mins_sec(event.end),
                                                                 hrs_mins_sec(event.end - event.start))
        (start_col, end_col) = colspan(event.start, event.end)
        write_cols(start_col, end_col, event.description, event.format, comment=comment, border=True)

    def write_events(events):
        for e in deconflict(events):
            write_event(e)

    worksheet.set_column(0, 0, 30)  # width of first column

    if title:
        write_cols(0, 0, title, FMT.bold)
        row += 1

    # write time axis row
    write_cols(0, 0, "Time: hr:min", FMT.bold)
    for t in range(start_time, end_time, timestep):
        col = start_col(t)
        worksheet.set_column(col, col, 1, get_format({'left': 5, 'border_color': '#d4d4d4'}))
        write_cols(col, start_col(t + timestep) - 1, hrs_mins(t),
                        {'left': 5, 'border_color': '#d4d4d4', 'bold': True}, merge=True)
    row += 1

    worksheet.set_column(1, 1 + (end_time - start_time),
                              1)  # width of all subseqeunt columns (1 increment of time)

    hidden = set()

    for indent, row_instance in rows.visit_rows():
        write_cols(0, 0, row_instance.label, format=row_instance.format, indent=indent) # write row label
        write_events(row_instance.events)

        # if a row is collapsed, all its children (recursively) are hidden
        if row_instance.collapsed:
            hidden.update([r for _, r in row_instance.child_rows.visit_rows()])

        # now apply formatting to the row as a whole (not just the label i.e. first col)
        format = {'level': indent, 'collapsed': row_instance.collapsed, 'hidden': row_instance in hidden}
        worksheet.set_row(row, None, None, format)
        row += 1

    worksheet.freeze_panes(1, 1)

    workbook.close()
