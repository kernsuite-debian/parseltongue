# Copyright (C) 2005 Associated Universities, Inc. Washington DC, USA.
# Copyright (C) 2005 Joint Institute for VLBI in Europe
#
# This program is free software; you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation; either version 2 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.

# You should have received a copy of the GNU General Public License
# along with this program; if not, write to the Free Software
# Foundation, Inc., 59 Temple Place, Suite 330, Boston, MA  02111-1307  USA
#
#  Correspondence concerning this software should be addressed as follows:
#         Internet email: bcotton@nrao.edu.
#         Postal address: William Cotton
#                         National Radio Astronomy Observatory
#                         520 Edgemont Road
#                         Charlottesville, VA 22903-2475 USA
#-----------------------------------------------------------------------
#
#                   Obit tasking interface
#
#  This module contains classes useful for an Obit tasking interface to python.
#  An ObitTask object contains input parameters for a given Obit program.
#     The parameters for a given task are defined in a Task Definition File
#  (TDF) which gives the order, names, types, ranges and dimensionalities.
#  A TDF is patterened after AIPS HELP files.
#     The Task Definition File can be derived from the AIPS Help file with the
#  addition of:
#   - A line before the beginning of each parameter definition of the form:
#   **PARAM** [type] [dim]
#       where [type] is float or str (string) and [dim] is the 
#       dimensionality as a blank separated list of integers, e.g.
#       **PARAM** str 12 5       (5 strings of 12 characters)
#   HINT: No matter what POPS thinks, all strings are multiples of 4 characters
#   For non AIPS usage dbl (double), int (integer=long), boo (boolean)
#   are defined.
#
#-----------------------------------------------------------------------

# Bits from AIPS.
from AIPSUtil import ehex

# Bits from the generic Task implementation.
from Proxy.Task import Task

# Generic Python stuff.
import fcntl, glob, os, pickle, select, struct, string, pty


class _ObitTaskParams:
    def __parse(self, name):
        """Determine the proper attributes for the Obit task NAME by
        parsing its TDF file."""

        task = None
        strlen = None
        deff = [0]
        gotDesc = False
        min = None
        max = None

	#print "DEBUG in ObitTaskParams"

        path = os.environ['OBIT'] + '/TDF/' + name + '.TDF'
        input = open(path)
        for line in input:
            # DEBUG
            #print line
            # A line of dashes terminates the parameter definitions.
            if line.startswith('--------'):
                break;

            # Comment lines start with ';'.
            if line.startswith(';'):
                continue

            if not task:
                task = line.split()[0]
                min_start = line.find('LLLLLLLLLLLL')
                min_end = line.rfind('L')
                max_start = line.find('UUUUUUUUUUUU')
                max_end = line.rfind('U')
                dir_start = min_start - 2
                dir_end = min_start - 1
                continue

            if line.startswith(task):
                continue

            if line.startswith(' ') or line.startswith('\n'):
                continue

            # Description of parameter?
            if line.startswith('**PARAM**'):
                gotDesc = True
                # Get type and dimension.
                parts = line.split()
                 # Dimensionality.
                dim = []
                total = 1
                for x in parts[2:]:
                    total *= int(x)
                    dim.append(int(x));
                # Want number of strings, not number of characters.
                if parts[1] == 'str':
                    total = total / dim[0]
                # Type.
                type = parts[1]
                if type == 'float':
                    type = float
                    strlen = None
                    deff = total * [0.0]
                elif type == 'str':
                    type = str
                    strlen = dim[0]
                    deff = total * [strlen * ' ']
                elif type == 'int':
                    type = int
                    strlen = None
                    deff = total * [0]
                elif type == 'boo':
                    type = bool
                    strlen = None
                    deff = total * [False]
                # print "DEBUG line",line,type,dim

            # If just parsed PARAM line get parameter.
            elif gotDesc:
                gotDesc = False
                adverb = line.split()[0]
                code = line[min_start - 1:min_start]
                if not code:
                    code = ' '
                try:
                    min = float(line[min_start:min_end].strip())
                    max = float(line[max_start:max_end].strip())
                except:
                    min = None
                    max = None

                # Assume type/dimension is one just read.
                # If only one entry, convert deff to scalar.
                if len(deff) == 1:
                    deff = deff[0]
                self.default_dict[adverb] = deff # default
                self.dim_dict[adverb] = dim # dimensionality
                if code in ' *&$' or len(adverb) > 9:
                    self.input_list.append(adverb)
                if code in '&%$@':
                    self.output_list.append(adverb)
                if strlen:
                    self.strlen_dict[adverb] = strlen
                if min != None:
                    self.min_dict[adverb] = min
                if max != None:
                    self.max_dict[adverb] = max
                #print "DEBUG adverb", adverb, deff, dim

        # Parse HELP section.
        for line in input:
            # A line of dashes terminates the help message.
            if line.startswith('--------'):
                break;

            self.help_string = self.help_string + line

    def __init__(self, name, version):
        self.default_dict = {}
        self.input_list = []
        self.output_list = []
        self.min_dict = {}
        self.max_dict = {}
        self.strlen_dict = {}
        self.help_string = ''
        self.dim_dict = {}

        self.name = name
        if version in ['OLD', 'NEW', 'TST']:
            self.version = os.path.basename(os.environ[version])
        else:
            self.version = version

        path = os.environ['HOME'] + '/.ParselTongue/' \
               + self.version + '/' + name + '.pickle'

        try:
            unpickler = pickle.Unpickler(open(path))
            self.default_dict = unpickler.load()
            self.input_list = unpickler.load()
            self.output_list = unpickler.load()
            self.min_dict = unpickler.load()
            self.max_dict = unpickler.load()
            self.strlen_dict = unpickler.load()
            self.dim_dict = unpickler.load()
            self.help_string = unpickler.load()
        except (IOError, EOFError):
            self.__parse(name)

            # Make sure the directory exists.
            if not os.path.exists(os.path.dirname(path)):
                os.makedirs(os.path.dirname(path))

            pickler = pickle.Pickler(open(path, mode='w'))
            pickler.dump(self.default_dict)
            pickler.dump(self.input_list)
            pickler.dump(self.output_list)
            pickler.dump(self.min_dict)
            pickler.dump(self.max_dict)
            pickler.dump(self.strlen_dict)
            pickler.dump(self.dim_dict)
            pickler.dump(self.help_string)

    # Provide a dictionary-like interface to deal with the
    # idiosyncrasies of XML-RPC.
    def __getitem__(self, key):
        return self.__dict__[key]


class ObitTask(Task):
    def __init__(self):
        Task.__init__(self)
        self._params = {}
        self._popsno = {}

    def params(self, name, version):
        """Return parameter set for version VERSION of task NAME."""
        return _ObitTaskParams(name, version)

    def __write_adverb(self, params, file, adverb, value):
        """Write Obit input text file."""

        assert(adverb in params.input_list)

        # Get type, may be scalar or list
        dtype = type(value)
        if dtype == list:
            dtype = type(value[0])

        # Convert to string for numeric types
        if type(value) == list:
            data = string.join(map(str, value))
        else:
            data = str(value)

        dim = params.dim_dict[adverb]   # Dimensionality array
        dimStr = "(" + str(dim[0]) + ")"
        if (len(dim) > 1):
            if (dim[1] > 1):
                dimStr = "(" + str(dim[0]) + "," + str(dim[1]) + ")"

        if dtype == float:
            file.write("$Key = " + adverb + " Flt " + dimStr + "\n")
            file.write(data + "\n")     # Write data to file
        elif dtype == str:
            file.write("$Key = " + adverb + " Str " + dimStr + "\n")
            if type(value) == list:
                for x in value:
                    file.write(x + "\n") # Write data to file
            else:
                #print "DEBUG write_adverb", adverb, dtype, dim, value
                file.write(value + "\n") # Write data to file
        elif dtype == bool:
            file.write("$Key = " + adverb + " Boo " + dimStr + "\n")
            if type(value) == list:
                #print "DEBUG value", adverb, value
                for x in value:
                    if x:
                        file.write(" T") # Write data to file.
                    else:
                        file.write(" F")
            else:
                if value:
                    file.write(" T")    # Write data to file.
                else:
                    file.write(" F")
            file.write("\n")
        elif dtype == int:
            file.write("$Key = " + adverb + " Int " + dimStr + "\n")
            file.write(data + "\n" )    # Write data to file.
        else:
            #print "DEBUG ObitTask adverb", adverb, dim, dtype
            raise AssertionError, type(value)

    def __read_adverb(self, params, file, adverb):
        """read value from output file."""

        assert(adverb in params.output_list)

        gotIt = False    # Not yet found entry
        count = 0        # no values parset yet
        total = 1
        value = []       # to accept
        for line in file:
            # DEBUG
            #print line
            # Look for header for parameter
            if line.startswith("$Key  " + adverb):
                gotIt = True
                parts = string.split(line)
                # How many values
                total = 1
                # DEBUG print parts  
                for x in parts[3:]:
                    total *= int(x)
                dtype  = parts[2]
                if type=="str":
                    total = total / parts[3] # Number of strings.

            # Read data one value per line after 'gotIt'.
            elif gotIt:
                # DEBUG print "gotIt", type, line
                if dtype == 'Flt':
                    value.append(float(line))
                elif dtype == 'Dbl':
                    value.append(float(line))
                elif dtype == 'Str':
                    value.append(line)
                elif dtype == 'Int':
                    value.append(int(line))
                elif dtype == 'Boo':
                    if line.startswith('T'):
                        value.append(True)
                    else:
                        value.append(False)
                count = count + 1

            if gotIt and count >= total:  # Finished?
                    break

        # Convert to scalar if only one.
        if len(value)==1:
            value = value[0]
        # Done
        # DEBUG print "fetch adverb", adverb, value
        return value

    def spawn(self, name, version, userno, msgkill, isbatch, input_dict):
        """Start the task."""

        params = _ObitTaskParams(name, version)
        popsno = _allocate_popsno()
        index = popsno - 1

        # Set input and output text parameter/result files
        tmpInput = "/tmp/" + params.name + "Input." + str(popsno)
        tmpOutput = "/tmp/" + params.name + "Output." + str(popsno)

        in_file = open(tmpInput, mode="w")

        for adverb in params.input_list:
            self.__write_adverb(params, in_file, adverb, input_dict[adverb])

        in_file.close()

        # If debugging add a link to the input file to preserve it.
        if input_dict['DEBUG']:
            tmpDebug = tmpInput + 'Dbg'
            if os.access(tmpDebug, os.F_OK):
                os.unlink(tmpDebug)     # Remove any old version file.
            os.link(tmpInput, tmpDebug) # Add new link.
            # Tell about it.
            print "Saving copy of Obit task input in" + tmpDebug

        path = os.environ['OBIT'] +'/bin/' + os.environ['ARCH'] + '/' + name
        arglist = [name, "-input", tmpInput, "-output", tmpOutput,
                   "-pgmNumber", str(popsno), "-AIPSuser", str(userno)]
        tid = Task.spawn(self, path, arglist)
        self._params[tid] = params
        self._popsno[tid] = popsno
        return tid

    def messages(self, tid):
        """Return task's messages."""

        # Add a default priority to the messages
        messages = Task.messages(self, tid)
        return [(1, msg) for msg in messages]

    def wait(self, tid):
        """Wait for the task to finish."""

        assert(self.finished(tid))

        params = self._params[tid]
        popsno = self._popsno[tid]
        index = popsno - 1

        tmpInput = "/tmp/" + params.name + "Input." + str(popsno)
        tmpOutput = "/tmp/" + params.name + "Output." + str(popsno)

        output_dict = {}
        for adverb in params.output_list:
            # Need to parse whole file each time as order not specified
            out_file = open(tmpOutput, mode='r')
            output_dict[adverb] = self.__read_adverb(params, out_file, adverb)
            out_file.close()

        if os.access(tmpInput, os.F_OK):
            os.unlink(tmpInput)         # Remove input file.
        if os.access(tmpOutput, os.F_OK):
            os.unlink(tmpOutput)        # Remove output file.

        _free_popsno(popsno)

        del self._params[tid]
        del self._popsno[tid]
        Task.wait(self, tid)

        return output_dict


# In order to prevent multiple Obit instances from using the same POPS
# number, every Obit instance creates a lock file in /tmp.  These lock
# files are named Obitx.yyy, where x is the POPS number (in extended
# hex) and yyy is the process ID of the Obit instance.

def _allocate_popsno():
    for popsno in range(1,16):
        # In order to prevent a race, first create a lock file for
        # POPSNO.
        try:
            path = '/tmp/Obit' + ehex(popsno, 1, 0) + '.' + str(os.getpid())
            fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0666)
            os.close(fd)
        except:
            continue

        # Get a list of likely lock files and iterate over them.
        # Leave out our own lock file though.
        files = glob.glob('/tmp/Obit' + ehex(popsno, 1, 0) + '.[0-9]*')
        files.remove(path)
        for file in files:
            # If the part after the dot isn't an integer, it's not a
            # proper lock file.
            try:
                pid = int(file.split('.')[1])
            except:
                continue

            # Check whether the Obit instance is still alive.
            try:
                os.kill(pid, 0)
            except:
                # The POPS number is no longer in use.  Try to clean
                # up the lock file.  This might fail though if we
                # don't own it.
                try:
                    os.unlink(file)
                except:
                    pass
            else:
                # The POPS number is in use.
                break
        else:
            # The POPS number is still free.
            return popsno

        # Clean up our own mess.
        os.unlink(path)

    raise RuntimeError, "No free Obit POPS number available on this system"

def _free_popsno(popsno):
    path = '/tmp/Obit' + ehex(popsno, 1, 0) + '.' + str(os.getpid())
    os.unlink(path)
