from __future__ import absolute_import
from __future__ import division
from __future__ import print_function

import functools

import numpy as np

from .. import Variable
from ..core.utils import (FrozenOrderedDict, Frozen,
                          NdimSizeLenMixin, DunderArrayMixin)
from ..core import indexing
from ..core.pycompat import integer_types

from .common import AbstractDataStore, DataStorePickleMixin


class NioArrayWrapper(NdimSizeLenMixin, DunderArrayMixin):

    def __init__(self, variable_name, datastore):
        self.datastore = datastore
        self.variable_name = variable_name
        array = self.get_array()
        self.shape = array.shape
        self.dtype = np.dtype(array.typecode())

    def get_array(self):
        self.datastore.assert_open()
        return self.datastore.ds.variables[self.variable_name]

    def __getitem__(self, key):
        if isinstance(key, indexing.VectorizedIndexer):
            raise NotImplementedError(
                'Nio backend does not support vectorized indexing. Load your '
                'data first with .load() or .compute(). Given {}'.format(key))
        # Nio only supports slice indexing, not an array
        if (isinstance(key, indexing.OuterIndexer) and
                not all(isinstance(k, (integer_types, slice)) for k in key)):
            raise NotImplementedError(
                'Nio backend does not support indexing with array keys. Load '
                'your data first with .load() or .compute(). '
                'Given {}'.format(key))
        key = indexing.to_tuple(key)
        with self.datastore.ensure_open(autoclose=True):
            array = self.get_array()
            if key == () and self.ndim == 0:
                return array.get_value()
            return array[key]


class NioDataStore(AbstractDataStore, DataStorePickleMixin):
    """Store for accessing datasets via PyNIO
    """
    def __init__(self, filename, mode='r', autoclose=False):
        import Nio
        opener = functools.partial(Nio.open_file, filename, mode=mode)
        self.ds = opener()
        # xarray provides its own support for FillValue,
        # so turn off PyNIO's support for the same.
        self.ds.set_option('MaskedArrayMode', 'MaskedNever')
        self._autoclose = autoclose
        self._isopen = True
        self._opener = opener
        self._mode = mode

    def open_store_variable(self, name, var):
        data = indexing.LazilyIndexedArray(NioArrayWrapper(name, self))
        return Variable(var.dimensions, data, var.attributes)

    def get_variables(self):
        with self.ensure_open(autoclose=False):
            return FrozenOrderedDict((k, self.open_store_variable(k, v))
                                     for k, v in self.ds.variables.items())

    def get_attrs(self):
        with self.ensure_open(autoclose=True):
            return Frozen(self.ds.attributes)

    def get_dimensions(self):
        with self.ensure_open(autoclose=True):
            return Frozen(self.ds.dimensions)

    def get_encoding(self):
        encoding = {}
        encoding['unlimited_dims'] = set(
            [k for k in self.ds.dimensions if self.ds.unlimited(k)])
        return encoding

    def close(self):
        if self._isopen:
            self.ds.close()
            self._isopen = False
