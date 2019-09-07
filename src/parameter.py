# Built-in modules
import numpy as np
import sys as sy

# BoloCalc modules
import src.unit as un
import src.distribution as ds


class Parameter:
    """
    Parameter object contains attributes for input and output parameters.
    If 'inp' argument is a float, one band is assumed; if it is a list,
    len(list) bands are assumed.

    Args:
    log (src.Logging): logging object
    name (str): parameter name
    inp (str or src.Distribution): parameter value(s)
    unit (src.Unit): parameter unit. Defaults to src.Unit('NA')
    min (float): minimum allowed value. Defaults to None
    max (float): maximum allowe value. Defaults to None
    type (type): cast parameter data type. Defaults to numpy.float

    Attributes
    name (str): where the 'name' arg is stored
    unit (src.Unit): where the 'unit' arg is stored
    type (type): where the 'type' arg is stored
    """

    def __init__(self, log, inp, std_param=None, name=None, unit=None,
                 min=None, max=None, inp_type=float, band_ids=None):
        # Store passed arguments
        self._log = log
        # If a StandardParam object is passed, use its attributes
        if std_param is not None:
            self.name = std_param.name
            self.unit = std_param.unit
            self._min = std_param.min
            self._max = std_param.max
            self._type = std_param.type
        # Otherwise, store the passed attributes
        else:
            self.name = name
            if unit is not None:
                self.unit = unit
            else:
                self.unit = un.Unit("NA")  # 1
            if min is not None:
                self._min = float(min)
            else:
                self._min = None
            if max is not None:
                self._max = float(max)
            else:
                self._max = None
            self._type = inp_type
        # For storing parameters of type [m1, m2, ...] +/- [s1, s2, ...]
        self._band_ids = band_ids

        # Spread delimiter
        self._spread_delim = '+/-'
        # Allowed parameter string values when input type is float
        self._float_str_vals = ["NA", "BAND"]

        # Store the parameter value, mean, and standard deviation
        self._store_param(inp)
        # Check that the value is within the allowed range
        self._check_range()

    # ***** Public Methods *****
    def fetch(self, band_id=1):
        """
        Return (avg, med, std) given a band_id, or return (val)

        Args:
        band_id (int): band ID indexed from 1. Defaults to 1.
        """
        if self._val is not None and self._avg is None:
            return (self._val, self._val, 'NA')
        if self._mult_bands:
            return (self._avg[band_id - 1],
                    self._med[band_id - 1],
                    self._std[band_id - 1])
        else:
            return (self._avg,
                    self._med,
                    self._std)

    def change(self, new_avg, new_std=None, band_id=1):
        """
        Change self._avg to new_avg and self._std to new_std

        Args:
        new_avg (int or list): new value to be set

        Return 'True' if avg or std value was altered, 'False' if not
        """
        # Bool to return indicating whether or not parameter changed
        ret_bool = False
        # Set parameter to a new string
        if isinstance(new_avg, str) or isinstance(new_avg, np.string_):
            avg_new = new_avg
            if self._mult_bands:
                if self._avg[band_id - 1].upper() != avg_new.upper():
                    self._avg[band_id - 1] = avg_new
                    ret_bool = True
                else:
                    ret_bool = False
            else:
                if self._avg.upper() != avg_new.upper():
                    self._avg = avg_new
                    ret_bool = True
                else:
                    ret_bool = False
        # Set parameter to a new float
        elif isinstance(new_avg, float) or isinstance(new_avg, np.float_):
            # Convert to SI units
            avg_new = self.unit.to_SI(new_avg)
            # Change the parameter if it currently has no value
            if self._is_empty(band_id):
                if self._mult_bands:
                    self._avg[band_id - 1] = avg_new
                else:
                    self._avg = avg_new
                ret_bool = True
                return ret_bool
            if self._mult_bands:
                # Change the parameter if it's different to within 5 sig figs
                if (self._sig_figs(avg_new, 5) !=
                   self._sig_figs(self._avg[band_id - 1], 5)):
                    self._avg[band_id - 1] = avg_new
                    ret_bool = True
                if new_std is not None:
                    std_new = self.unit.to_SI(new_std)
                    if (self._sig_figs(std_new, 5) !=
                       self._sig_figs(self._std[band_id - 1], 5)):
                        self._std[band_id - 1] = std_new
                        ret_bool = True
            else:
                # Change the parameter if it's different to within 5 sig figs
                if (self._sig_figs(avg_new, 5) !=
                   self._sig_figs(self._avg, 5)):
                    self._avg = avg_new
                    ret_bool = True
                if new_std is not None:
                    std_new = self.unit.to_SI(new_std)
                    if (self._sig_figs(std_new, 5) !=
                       self._sig_figs(self._std, 5)):
                        self._std = std_new
                        ret_bool = True
        else:
            self._log.err(
                "Could not change parameter '%s' to value '%s' of type '%s'"
                % (str(self.name), str(new_avg), str(type(new_avg))))
        return ret_bool

    def get_val(self):
        """ Return the input value """
        return self._val

    def get_avg(self, band_id=1):
        """
        Return average value for band_id

        Args:
        band_id (int): band ID indexed from 1. Defaults to 1.
        """
        return self.fetch(band_id)[0]

    def get_med(self, band_id=1):
        """
        Return average value for band_id

        Args:
        band_id (int): band ID indexed from 1. Defaults to 1.
        """
        return self.fetch(band_id)[1]

    def get_std(self, band_id=1):
        """
        Return standard deviation for band_id

        Args:
        band_id (int): band ID indexed from 1. Defaults to 1.
        """
        return self.fetch(band_id)[2]

    def sample(self, band_id=1, nsample=1, min=None, max=None, null=False):
        """
        Sample parameter distribution for band_id nsample times
        and return the sampled values in an array if nsample > 1
        or as a float if nsample = 1.

        Args:
        band_id (int): band ID indexes from 1. Defaults to 1.
        nsample (int): number of samples to draw from distribution
        min (float): the minimum allowed value to be returned
        max (float): the maximum allowed value to be returned
        """
        # If min and max not explicitly passed, use constructor values
        if min is None:
            min = self._min
        if max is None:
            max = self._max
        # If this parameter is 'NA' or 'BAND', return said string
        if self._is_empty():
            return str(self._avg).strip().upper()
        # If this parameter is a distribution, sample it
        elif isinstance(self._val, ds.Distribution):
            return self._val.sample(nsample=nsample)
        # Otherwise, sample the Gaussian described by mean +/- std
        else:
            vals = self.fetch(band_id)
            avg = vals[0]
            std = vals[2]
            # If std is zero (or less than), return the average value
            if std is "NA" or np.any(std <= 0.):
                return avg
            # If the user calls for a null sampling, set avg to zero
            if null:
                avg = 0.
            if nsample == 1:
                samp = np.random.normal(avg, std, nsample)[0]
            else:
                samp = np.random.normal(avg, std, nsample)
            # Check that the sampled value doesn't surpasse the max or min
            if min is not None and samp < min:
                return min
            if max is not None and samp > max:
                return max
            return samp

    # ***** Helper Methods *****
    def _store_param(self, inp):
        # Bools only passed from simulationInputs.txt
        if self._type is bool:
            self._store_bool(inp)
        # Ints passed for num_det, num_ot, etc.
        elif self._type is int:
            self._store_int(inp)
        # Floats passed for mean +/- std values
        # This is most common
        elif self._type is float:
            self._store_float(inp)
        # Strs passed for, for example, Site
        elif self._type is str:
            self._store_str(inp)
        # List passed for simulationInputs CL values
        elif self._type is list:
            self._store_list(inp)
        else:
            self._log.err(
                "Passed paramter '%s' not one of allowed data types: \
                bool, float, int, str, list" % (self.name))
        return True

    def _store_bool(self, inp):
        self._mult_bands = False
        val = inp.lower().capitalize().strip()
        if val != "True" and val != "False":
            self._log.err(
                "Failed to parse boolean input '%s'" % (inp))
        self._val = eval(val)
        self._avg = None
        self._med = None
        self._std = None
        return

    def _store_int(self, inp):
        self._mult_bands = False
        try:
            self._val = None
            self._avg = int(inp)
            self._med = self._avg
            self._std = 0.
        except ValueError:
            self._log.err(
                    "Parameter '%s' with value '%s' cannot be type "
                    "casted to int" % (self.name, str(inp)))
        return

    def _store_float(self, inp):
        # If input is a string, then one of the following
        # '[m1, m2, ...] +/- [s1, s2, ...]' or 'm +/- s' or 'm'
        if isinstance(inp, str):
            self._store_float_str(inp)
        # If input distribution, then simply store it
        elif isinstance(inp, ds.Distribution):
            self._store_float_dist(inp)
        # If input tuple, we are dealing with an optic, which
        # may have distributions for any frequency channel
        # (param_str, dist_dict)
        # param_str is assumed to be identical to what's handled for a string
        # e.g. '[m1, m2, ...] +/- [s1, s2, ...]' or 'm +/- s' or 'm'
        # dist_dict is assumed to be a dictionary of possible dist objs
        # keyed by Band ID
        elif isinstance(inp, tuple):
            self._store_float_tuple(inp)
        # If none of the above, throw an error
        else:
            self._log.err(
                "Problem handling Paramter '%s' of input type 'float.' "
                "Input value not a string, src.Distribution, or tuple"
                % (self.name))
        return

    def _store_float_str(self, inp):
        # Check for the spread format
        # [m1, m2, ...] +/- [s1, s2, ...]
        # m +/- s
        if self._spread_delim in inp:
            self._val = None
            vals = inp.split(self._spread_delim)
            self._avg = self._float(vals[0])
            self._med = self._avg
            self._std = self._float(vals[1])
        # Otherwise, no spread, and therefore no std
        else:
            self._val = None
            self._avg = self._float(inp)
            self._med = self._avg
            self._std = self._zero(self._avg)
        return

    def _store_float_dist(self, inp):
        self._mult_bands = False
        self._val = inp
        self._avg = self._float(inp.mean())
        self._med = self._float(inp.median())
        self._std = self._float(inp.std())
        return

    def _store_float_tuple(self, inp):
        # Presumed format (param_str, dict_dist), which only comes about for
        # optics distributions
        if len(inp) != 2:
            self._log.err(
                "More or less than two elements in float_tuple '%s' in for "
                "Parameter '%s' "
                % (str(inp), self.name))
        param_str = inp[0]
        dist_dict = inp[1]
        # If there is no distribution dictionary passed, then process
        # the input string as normal
        if dist_dict is None:
            self._store_float_str(param_str)
            return
        # Otherwise, there is a PDF to be processed
        pdf_conv_dict = {'PDF': str('PDF')}  # dict for helping eval()
        # Split the input string using +/-
        if self._spread_delim in param_str:
            vals = param_str.split(self._spread_delim)
            # Each should evaluate to a list, float, or string
            mean_val = eval(vals[0], pdf_conv_dict)
            std_val = eval(vals[1], pdf_conv_dict)
        else:
            # Should evaluate to list, float, or string
            mean_val = eval(param_str, pdf_conv_dict)
            std_val = None
        # Figure out which bands want to use a PDF
        # Is the input a list of values? If so, then multiple bands
        if isinstance(mean_val, list):
            self._mult_bands = True
            # Std also needs to be a list
            if std_val is not None and not isinstance(std_val, list):
                self._log.err(
                    "Mean values '%s' a list for optic paramter "
                    "'%s' but std values '%s' not a list"
                    % (str(mean_val), self.name, str(std_val)))
            # The std list needs to be the same length as the mean list
            if std_val is not None and len(mean_val) != len(std_val):
                self._log.err(
                    "Mean value list '%s' and std value list '%s' "
                    "for optic parameter '%s' not the same length"
                    % (str(mean_val), str(std_val), self.name))
            # Channel values stored in channel dict order
            self._val = []
            self._avg = []
            self._med = []
            self._std = []
            # Loop over mean values, checking for distributions
            for i, mv in enumerate(mean_val):
                if std_val is not None:
                    sv = std_val[i]
                else:
                    sv = 0.
                # If mean value is 'PDF', find its distribution in the
                # passed distribution dictionary
                if 'PDF' in str(mv).upper():
                    if self._band_ids is None:
                        self._log.err(
                            "'PDF' found in Parameter '%s' but no band_ids "
                            "passed to Parameter() constructor" % (self.name))
                    # Idenfity the distribution using the Band ID
                    band_id = self._band_ids[i].upper()
                    try:
                        dist = dist_dict[band_id]
                    except KeyError:
                        self._log.err(
                            "Could not find Distribution for optic "
                            "paramter '%s' and Band ID '%s'"
                            % (self.name, band_id))
                    self._val.append(dist)
                    self._avg.append(dist.mean())
                    self._med.append(dist.median())
                    self._std.append(dist.std())
                else:
                    self._val.append(None)
                    self._avg.append(float(mv))
                    self._med.append(float(mv))
                    self._std.append(float(sv))
        # If the mean value is a string, then the value covers all bands
        elif isinstance(mean_val, str):
            self._mult_bands = False
            # Check if the parameter is given by a PDF
            if 'PDF' in mean_val.upper():
                # Single value named 'PDF' is assumed to define
                # a parameter distribution for all bands
                try:
                    dist = dist_dict['ALL']
                except KeyError:
                    self._log.err(
                        "Could not find Distribution for optic "
                        "paramter '%s' and Band ID '%s'"
                        % (self.name, band_id))
                self._val = dist
                self._avg = dist.mean()
                self._med = dist.median()
                self._std = dist.std()
            else:
                self._log.err(
                    "Could not understand mean value '%s' for Parameter '%s'"
                    % (self.name))
        # If the mean value is a float or an int, then simply store the
        # values straight away
        elif isinstance(mean_val, float) or isinstance(mean_val, int):
            self._val = None
            self._avg = mean_val
            self._med = mean_val
            if std_val is not None:
                if not isinstance(std_val, float) or isinstance(std_val, int):
                    self._log.err(
                        "Std value '%s' for Parameter '%s' is not a float "
                        "or int even though its mean value '%s' is"
                        % (str(std_val), self.name, str(mean_val)))
                self._std = std_val
            else:
                self._std = 0.
        else:
            self._log.err(
                "Could characterize mean value '%s' for Parameter '%s'"
                % (str(mean_val), self.name))
        return

    def _store_list(self, inp):
        self._mult_bands = False
        self._val = eval(inp)
        self._avg = None
        self._med = None
        self._std = None
        if type(self._val) is not list:
            self._log.err(
                "Parameter '%s' with value '%s' cannot be type "
                "casted to list" % (self.name, str(inp)))
        return

    def _store_str(self, inp):
        self._mult_bands = False
        self._val = str(inp)
        self._avg = None
        self._med = None
        self._std = None
        return

    def _float(self, val):
        """ Convert val to an array of or single float(s) """
        # If the passed value is None, return it right back
        if val is None:
            self._mult_bands = False
            return None
        # Try to convert the value to a float. If successful,
        # convert to SI units and return
        try:
            float_val = float(val)
            self._mult_bands = False
            return self.unit.to_SI(float_val)
        # If unable to convert to a float...
        except ValueError:
            # Try to convert to a numpy array of floats. If successful,
            # convert to an array of SI unit floats and return
            try:
                arr_val = np.array(eval(val)).astype(float)
                self._mult_bands = True
                return self.unit.to_SI(arr_val)
            # If that fails, look for a special string
            except:
                # The final option is to accpet either "BAND" or "NA"
                self._mult_bands = False
                ret = str(val).strip().upper()
                if ret in self._float_str_vals:
                    return ret
                # Otherwise throw an error
                else:
                    self._log.err(
                        "Passed parameter '%s' with value '%s' cannot be type "
                        "casted to float" % (self.name, str(val)))
        return

    def _zero(self, val):
        """Convert val to an array of or single zero(s)"""
        try:
            return np.zeros(len(val))
        except:
            return 0.

    def _check_range(self):
        if self._avg is None or isinstance(self._avg, str):
            return True
        else:
            avg = np.array(self._avg)
            if self._min is not None and np.any(avg < self._min):
                self._log.err(
                    "Passed value %s for parameter %s lower than the mininum \
                    allowed value %f" % (
                        str(self._avg), self.name, self._min), 0)
            elif self._max is not None and np.any(avg > self._max):
                self._log.err(
                    "Passed value %s for parameter %s greater than the maximum \
                    allowed value %f" % (
                        str(self._avg), self.name, self._max))
            else:
                return True

    def _sig_figs(self, inp, sig):
        if inp == 0:
            return inp
        else:
            return round(inp, sig-int(np.floor(np.log10(abs(inp))))-1)

    def _is_empty(self, band_id=1):
        """ Check if a parameter is 'NA' """
        if self._mult_bands:
            if str(self._avg[band_id - 1]).upper() in self._float_str_vals:
                return True
            else:
                return False
        else:
            if str(self._avg).upper() in self._float_str_vals:
                return True
            else:
                return False
