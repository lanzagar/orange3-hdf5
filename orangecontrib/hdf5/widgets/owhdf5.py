from collections import namedtuple
import os
import sys

import h5py
from PyQt4 import QtGui
from PyQt4.QtCore import Qt
from PyQt4.QtGui import QApplication, QCursor, QMessageBox

from Orange.data import Table
from Orange.widgets import widget, gui
from Orange.widgets.settings import Setting


RecentPath = namedtuple(
    "RecentPath",
    ["abspath",   #: str # absolute path
     "prefix",    #: Option[str]  # BASEDIR | SAMPLE-DATASETS | ...
     "relpath"]   #: Option[str]  # path relative to `prefix`
)


class RecentPath(RecentPath):
    def __new__(cls, abspath, prefix, relpath):
        if os.name == "nt":
            # always use a cross-platform pathname component separator
            abspath = abspath.replace(os.path.sep, "/")
            if relpath is not None:
                relpath = relpath.replace(os.path.sep, "/")
        return super(RecentPath, cls).__new__(cls, abspath, prefix, relpath)

    @staticmethod
    def create(path, searchpaths):
        """
        Create a RecentPath item inferring a suitable prefix name and relpath.

        Parameters
        ----------
        path : str
            File system path.
        searchpaths : List[Tuple[str, str]]
            A sequence of (NAME, prefix) pairs. The sequence is searched
            for a item such that prefix/relpath == abspath. The NAME is
            recorded in the `prefix` and relpath in `relpath`.
            (note: the first matching prefixed path is chosen).

        """
        def isprefixed(prefix, path):
            """
            Is `path` contained within the directory `prefix`.

            >>> isprefixed("/usr/local/", "/usr/local/shared")
            True
            """
            normalize = lambda path: os.path.normcase(os.path.normpath(path))
            prefix, path = normalize(prefix), normalize(path)
            if not prefix.endswith(os.path.sep):
                prefix = prefix + os.path.sep
            return os.path.commonprefix([prefix, path]) == prefix

        abspath = os.path.normpath(os.path.abspath(path))
        for prefix, base in searchpaths:
            if isprefixed(base, abspath):
                relpath = os.path.relpath(abspath, base)
                return RecentPath(abspath, prefix, relpath)

        return RecentPath(abspath, None, None)

    def search(self, searchpaths):
        """
        Return a file system path, substituting the variable paths if required

        If the self.abspath names an existing path it is returned. Else if
        the `self.prefix` and `self.relpath` are not `None` then the
        `searchpaths` sequence is searched for the matching prefix and
        if found and the {PATH}/self.relpath exists it is returned.

        If all fails return None.

        Parameters
        ----------
        searchpaths : List[Tuple[str, str]]
            A sequence of (NAME, prefixpath) pairs.

        """
        if os.path.exists(self.abspath):
            return os.path.normpath(self.abspath)

        for prefix, base in searchpaths:
            if self.prefix == prefix:
                path = os.path.join(base, self.relpath)
                if os.path.exists(path):
                    return os.path.normpath(path)
        else:
            return None

    def resolve(self, searchpaths):
        if self.prefix is None and os.path.exists(self.abspath):
            return self
        elif self.prefix is not None:
            for prefix, base in searchpaths:
                if self.prefix == prefix:
                    path = os.path.join(base, self.relpath)
                    if os.path.exists(path):
                        return RecentPath(
                            os.path.normpath(path), self.prefix, self.relpath)
        return None

    @property
    def basename(self):
        return os.path.basename(self.abspath)

    @property
    def dirname(self):
        return os.path.dirname(self.abspath)


class OWHDF5(widget.OWWidget):
    name = "HDF5 Import"
    id = "orange.widgets.data.hdf5"
    description = """
    Load dataset from HDF5."""
    long_description = """
    Open a HDF5 file and load a data set from it."""
    icon = "icons/HDF5.svg"
    priority = 11
    category = "Data"
    keywords = ["data", "hdf5", "file", "load", "read"]

    outputs = [("Data", Table)]

    want_main_area = False
    resizing_enabled = False

    recent_paths = Setting([])

    dlgFormats = "HDF5 files (*.h5 *.hdf5 *.nxs *)"

    def __init__(self, parent=None):
        super().__init__(parent=parent)

        self.h5_file = None

        vbox = gui.widgetBox(self.controlArea, "HDF5 File", addSpace=True)
        box = gui.widgetBox(vbox, orientation=0)
        self.file_combo = QtGui.QComboBox(box)
        self.file_combo.setMinimumWidth(300)
        box.layout().addWidget(self.file_combo)
        self.file_combo.activated[int].connect(self.select_file)

        button = gui.button(box, self, '...', callback=self.browse_file)
        button.setIcon(self.style().standardIcon(QtGui.QStyle.SP_DirOpenIcon))
        button.setSizePolicy(
            QtGui.QSizePolicy.Maximum, QtGui.QSizePolicy.Fixed)

        button = gui.button(box, self, "Reload",
                            callback=self.reload, default=True)
        button.setIcon(
            self.style().standardIcon(QtGui.QStyle.SP_BrowserReload))
        button.setSizePolicy(
            QtGui.QSizePolicy.Fixed, QtGui.QSizePolicy.Fixed)

        box = gui.widgetBox(self.controlArea, "Data set", addSpace=True)
        self.dataset_combo = QtGui.QComboBox(box)
        self.dataset_combo.setMinimumWidth(300)
        #self.dataset_combo.sets
        box.layout().addWidget(self.dataset_combo)
        self.dataset_combo.activated[str].connect(self.open_dataset)
        self.infoa = gui.widgetLabel(box, 'No data loaded.')
        self.infob = gui.widgetLabel(box, ' ')
        self.warnings = gui.widgetLabel(box, ' ')
        #Set word wrap, so long warnings won't expand the widget
        self.warnings.setWordWrap(True)
        self.warnings.setSizePolicy(
            QtGui.QSizePolicy.Ignored, QtGui.QSizePolicy.MinimumExpanding)

        self.set_file_list()
        if len(self.recent_paths) > 0:
            self.open_file(self.recent_paths[0].abspath)

    def set_file_list(self):
        self.file_combo.clear()

        if not self.recent_paths:
            self.file_combo.addItem("(none)")
            self.file_combo.model().item(0).setEnabled(False)
        else:
            for i, recent in enumerate(self.recent_paths):
                self.file_combo.addItem(recent.basename)
                self.file_combo.model().item(i).setToolTip(recent.abspath)

    def set_dataset_list(self):
        self.dataset_combo.clear()
        for d in self.h5_file:
            self.dataset_combo.addItem(d)

    def reload(self):
        if self.recent_paths:
            return self.open_file(self.recent_paths[0].abspath)

    def select_file(self, n):
        if n < len(self.recent_paths):
            recent = self.recent_paths[n]
            del self.recent_paths[n]
            self.recent_paths.insert(0, recent)
        elif n:
            self.browse_file(True)

        if len(self.recent_paths) > 0:
            self.set_file_list()
            self.open_file(self.recent_paths[0].abspath)

    def browse_file(self):
        if self.recent_paths:
            start_file = self.recent_paths[0].abspath
        else:
            start_file = os.path.expanduser("~/")

        filename = QtGui.QFileDialog.getOpenFileName(
            self, 'Open HDF5 File', start_file, self.dlgFormats)
        if not filename:
            return

        searchpaths = []
        basedir = self.workflowEnv().get("basedir", None)
        if basedir is not None:
            searchpaths.append(("basedir", basedir))

        recent = RecentPath.create(filename, searchpaths)

        if recent in self.recent_paths:
            self.recent_paths.remove(recent)

        self.recent_paths.insert(0, recent)
        self.set_file_list()
        self.open_file(self.recent_paths[0].abspath)

    # Open a file, create data from it and send it over the data channel
    def open_file(self, fn):
        self.error()
        self.warning()
        self.information()

        if not os.path.exists(fn):
            dir_name, basename = os.path.split(fn)
            if os.path.exists(os.path.join(".", basename)):
                fn = os.path.join(".", basename)
                self.information("Loading '{}' from the current directory."
                                 .format(basename))
        if fn == "(none)":
            self.send("Data", None)
            self.infoa.setText("No data loaded")
            self.infob.setText("")
            self.warnings.setText("")
            return

        try:
            self.h5_file = h5py.File(fn)
        except Exception as exc:
            err_value = str(exc)
            self.error(err_value)
            self.infoa.setText('Unable to open HDF5 file.')
            self.infob.setText('Error:')
            self.warnings.setText(err_value)
        else:
            self.set_dataset_list()
            if self.dataset_combo.count():
                self.open_dataset(self.dataset_combo.currentText())

    def open_dataset(self, dataset):
        data = None
        try:
            dset = self.h5_file[dataset]
            data = Table(dset[:])
        except Exception as exc:
            err_value = str(exc)
            self.error(err_value)
            self.infoa.setText('Unable to load data set.')
            self.infob.setText('Error:')
            self.warnings.setText(err_value)

        if data is not None:
            self.infoa.setText("Shape: {}".format(data.X.shape))
            self.infob.setText("Type: {}".format(dset.dtype))
            self.warnings.setText("")
            data.name = dataset
        self.send("Data", data)


if __name__ == "__main__":
    a = QtGui.QApplication(sys.argv)
    ow = OWHDF5()
    ow.show()
    a.exec_()
    ow.saveSettings()
