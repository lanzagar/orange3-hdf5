#!/usr/bin/env python

from setuptools import setup

ENTRY_POINTS = {
    # Entry point used to specify packages containing widgets.
    'orange.widgets': (
        # Syntax: category name = path.to.package.containing.widgets
        'Data = orangecontrib.hdf5.widgets',
    ),

    # Register widget help
    "orange.canvas.help": (
        'html-index = orangecontrib.hdf5.widgets:WIDGET_HELP_PATH',)
}

KEYWORDS = (
    # [PyPi](https://pypi.python.org) packages with keyword "orange3 add-on"
    # can be installed using the Orange Add-on Manager
    'orange3 add-on',
)

if __name__ == '__main__':
    setup(
        name="Orange3 HDF5 Add-on",
        packages=['orangecontrib',
                  'orangecontrib.hdf5',
                  'orangecontrib.hdf5.widgets'],
        package_data={
            'orangecontrib.hdf5.widgets': ['icons/*'],
        },
        install_requires=['Orange3', 'h5py'],
        entry_points=ENTRY_POINTS,
        keywords=KEYWORDS,
        namespace_packages=['orangecontrib'],
        include_package_data=True,
        zip_safe=False,
    )
