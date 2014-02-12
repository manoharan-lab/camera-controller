from PyQt4 import QtGui, QtCore

def make_label(text, wordwrap=True):
    label = QtGui.QLabel()
    label.setText(text)
    if wordwrap:
        label.setWordWrap(True)
    return label


def make_VBox(items, parent=None):
    return fill_layout(QtGui.QVBoxLayout(parent), items)


def make_HBox(items, parent=None):
    return fill_layout(QtGui.QHBoxLayout(parent), items)


def fill_layout(layout, items):
    for item in items:
        if isinstance(item, int):
            layout.addStretch(item)
        elif isinstance(item, QtGui.QBoxLayout):
            layout.addLayout(item)
        else:
            if isinstance(item, basestring):
                item = make_label(item)
            layout.addWidget(item)
    return layout


def make_LineEdit(width, starting_text):
    line = QtGui.QLineEdit()
    line.setFixedWidth(width)
    line.setText(starting_text)
    return line


def make_button(label, callback, parent, shortcut=None, height=50, width=100,
                tooltip=None):
    """
    Handle the common boilerplate for creating buttons

    Parameters
    ----------
    label : string
        The label to display on the button
    callback : function
        The function to call when the button is clicked
    parent : QtGui.QWidget
        the parent widget
    height, width : int
        The dimensions of the button
    tooltip : string
        A tooltip for the button
    """
    button = QtGui.QPushButton(label, parent)
    button.clicked.connect(callback)
    button.setFixedHeight(height)
    button.setFixedWidth(width)
    if shortcut is not None:
        button.setShortcut(shortcut)
    if tooltip is not None:
        button.setToolTip(tooltip)
    return button

def make_control_group(parent, buttons, exclusive=True, default=None):
    controlgroup = QtGui.QButtonGroup(QtGui.QWidget(parent))
    for button in buttons:
        controlgroup.addButton(button)
        button.setCheckable(True)
    if default is not None:
        default.toggle()
    controlgroup.setExclusive(exclusive)

#def make_radio_group(labels, )
