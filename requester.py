import cookielib, urllib, urllib2, re, sys, logging
from abc import ABCMeta, abstractmethod

# filename='programLog.txt', 
logging.basicConfig(level=logging.DEBUG, format=' %(asctime)s - %(levelname)s - %(message)s')
#logging.disable(logging.CRITICAL)

# ---------
#  CLASSES
# ---------

class Handler:

    def __init__(self, fileName):
        self.fileName = fileName
        self.requests = []

        # Create opener with cookie support
        logging.debug('Configuring opener...')
        self.cookiejar = cookielib.CookieJar()
        self.opener = urllib2.build_opener(urllib2.HTTPCookieProcessor(self.cookiejar),
                                           urllib2.HTTPHandler(debuglevel=1))
        urllib2.install_opener(self.opener)

        self.inputs = {}
        self.parse()

    # Load the data of the file specified
    def parse(self):
        logging.debug('Loading input file data...')
        f = open(self.fileName, "r")
        content = f.read()
        f.close()

        self.requests = []

        # For each requests in the requests file (separated by a blank line)
        for reqLines in content.split("\n\n"):
            req = self.parseRequest(reqLines)
            if req: 
                self.requests.append(req)

    # Returns a Request obj. from the lines in which a expression is defined
    def parseRequest(self, req):

        # Replace items related to the global inputs
        for k, v in self.inputs.iteritems():
            req = req.replace("[[" + k + "]]", v)

        lines = req.split("\n")

        # The data to parse corresponds with the initialization configuration
        if lines and lines[0].replace(" ", "").upper() == "#INIT": 
            logging.debug('Initializing...')
            self.inputs = {}

            for line in lines:

                if re.match("^\s*#", line): # comment
                    logging.debug('Comment detected...%s' % line)
                    continue

                name, value = self.getPair(line, ":")
                name = name.strip().upper()

                if name == "INPUT":
                    for k in value.replace(" ", "").split(","):
                        self.inputs[k] = raw_input(k + ": ")
        else:
            method = "GET"
            url = ""
            params = None
            action = None

            for line in lines:
                # Get and format name and value of the command (ex: "METHOD : GET")
                name, value = self.getPair(line, ":")
                name = name.upper()

                if name == "URL":
                    url = value
                elif name == "METHOD":
                    method = value.upper()
                elif name == "PARAMS":
                    params = self.parseParams(value)
                elif name == "ACTION":
                    action = DownloadAction(url)

            if url != "":
                return RequestGroup(method, url, params, action)

        return None

    # Returns the params (in dictionary form) from the line that specifies them
    def parseParams(self, params_line):
        params = {}

        for param in params_line.split("&"):
            name, value = self.getPair(param, "=")
            params[name] = value

        return params

    # Separate name and value in a expression of the form: "NAME SEP VALUE"
    def getPair(self, pair, sep):
        tmp = pair.split(sep)
        name, value = tmp[0], sep.join(tmp[1:])
        return name.strip(), value.strip()

    def sendRequests(self):
        for req in self.requests:
            req.execute()

    def getInputs(self):
        return self.inputs


# Identifies a group of related requests
class RequestGroup:
    def __init__(self, method, url, params, action):
        self.url = url
        self.method = method
        self.params = params
        self.action = action

        # To store the url and params of the next request
        self.parsedUrl = self.url
        self.parsedParams = urllib.urlencode(self.params) if params != None else None

    def __str__(self):
        toRet = "%s %s" % (self.method, self.parsedUrl)

        if self.method == "GET" and self.parsedParams:
            toRet += "?%s" % self.parsedParams
        elif self.method == "POST":
            toRet += "\nData: %s" % self.parsedParams

        return toRet

    def execute(self):
        logging.debug("Executing request...")

        sources = self.extractSources()
        logging.debug("Sources: %s" % sources)

        if sources:
            for comb in SourceHandler(sources.values()):
                urlWithParams = self.url + ("?" + self.getParamsStr() if self.params else "")

                # Replace the data given in the sources in the url and params
                for k, v in zip(sources.keys(), comb):
                    urlWithParams = urlWithParams.replace(k, v)

                self.parsedUrl, self.parsedParams = self.getPair(urlWithParams, "?")

                logging.debug("Request details:")
                logging.debug(self)

                if self.action != None:
                    self.action.setUrl(urlWithParams)
                    self.action.execute()
                else:
                    content = self.send()
        else:
            content = self.send()

    # Converts the param dictionry in a string (params form)
    def getParamsStr(self):
        res = ""
        for k, v in self.params.iteritems():
            res += k + "=" + v + "&"
        return res[:-1]

    # Identifies, instance and return the needed sources related to the request group
    def extractSources(self):
        sources = {}   # dictionary with the sources, in the form { key: src }

        # Check if are special commands in the url
        spec, src = self.getSourceFromCmd(self.url)
        if src != None: 
            sources[spec] = src

        if self.params != None:
            for k, v in self.params.iteritems():
                # Check if are special commands in the key
                spec, src = self.getSourceFromCmd(k)
                if src != None: sources[spec] = src

                # Check if are special commands in the value
                spec, src = self.getSourceFromCmd(v)
                if src != None: sources[spec] = src

        return sources

    # Instance a source from the command given, of the form [[id:params]]
    def getSourceFromCmd(self, cmd):
        src = None
        spec = None
        match = re.match(r".*\[\[(.*)\]\].*", cmd)  # Special commands
        if match:
            sc_spec = self.getPair(match.group(1), ":")
            spec = "[[" + match.group(1) + "]]"

            sc_name = sc_spec[0].upper()
            sc_params = sc_spec[1:]

            if sc_name == "FILE":  # TODO: Check if file exists
                fileName = sc_params[0]
                src = FileSource(fileName)
            elif sc_name == "SEQ":
                seq = sc_params[0]
                src = SeqSource(seq)
            else:
                pass  # TODO: raise Exception
        return spec, src

    # Send the current request
    def send(self):
        url = self.parsedUrl

        if self.method == "GET":
            if self.parsedParams: url += "?" + self.parsedParams
            return urllib2.urlopen(url).read()
        elif self.method == "POST":
            return urllib2.urlopen(url, urllib.urlencode(self.parsedParams)).read()


    # Separate name and value in a expression of the form: "NAME SEP VALUE"
    def getPair(self, pair, sep):
        tmp = pair.split(sep)
        name, value = tmp[0], sep.join(tmp[1:])
        return name.strip(), value.strip()

# ----------
#  SOURCES
# ----------

# Parent for all the sources
class Source:
    __metaclass__ = ABCMeta

    def __iter__(self):
        return self

    @abstractmethod
    def next(self): pass

    @abstractmethod
    def reset(self): pass


# Iterate over the lines of a file
class FileSource(Source):
    def __init__(self, fileName):
        self.fileName = fileName
        self.data = None
        self.pointer = 0

    def next(self):
        if self.data == None:  # Avoids to load the resource if its not used
            self.data = [line.strip() for line in open(self.fileName, "r")]

            i = 0
            while i < len(self.data):
                if self.data[i] == "":
                    del self.data[i]
                i += 1
            print self.data

        if self.pointer < len(self.data):
            val = self.data[self.pointer]
            self.pointer += 1
            return val
        else:
            raise StopIteration()

    def reset(self):
        self.pointer = 0

# Iterate over a sequence, specified with a initial, a final one (inclusive) and a step
class SeqSource(Source):

    def __init__(self, strDef):
        try:
            params = map(lambda x: int(x), strDef.split(","))
            if len(params) != 3: raise SyntaxError

            self.ini, self.fin, self.step = params
            self.pointer = self.ini - self.step
        except SyntaxError:
            raise SyntaxError("Secuencia no valida")

    def next(self):
        if self.pointer < self.fin:
            self.pointer += self.step
            return str(self.pointer)
        else:
            raise StopIteration()

    def reset(self):
        self.pointer = self.ini - self.pointer


# Iterate through all the combinations of the sources given
class SourceHandler:
    def __init__(self, sources):
        self.sources = sources
        self.currValue = []

    def __iter__(self):
        return self

    def next(self, pos=0):
        p = len(self.sources) - 1

        if self.currValue == []:
            for s in self.sources:
                self.currValue.append(s.next())
            return self.currValue

        while p >= 0:
            try:
                self.currValue[p] = self.sources[p].next()
                return self.currValue
            except StopIteration:
                self.sources[p].reset()
                self.currValue[p] = self.sources[p].next()
                p -= 1
        raise StopIteration()


# ----------
#  ACTIONS
# ----------

# Parent for all the sources
class Action:
    __metaclass__ = ABCMeta

    def __init__(self, url, condition = None):  # self or external url
        self.url = url
        self.condition = condition

    @abstractmethod
    def conditionAccomplished(self): pass

    @abstractmethod
    def execute(self): pass

    def setUrl(self, url):
        self.url = url


class DownloadAction(Action):

    def conditionAccomplished(self):
        if self.condition:
            return True
        else:
            return False # TODO

    def execute(self):
        if self.conditionAccomplished():
            logging.debug("Downloading... (%s)" % self.url)
            urllib.urlretrieve(self.url, self.getFileName())

    def getFileName(self):
        baseNameAndParams = self.url.split("/")[-1].split("?")
        aux = baseNameAndParams[0].split(".")
        fileName, fileExt = ".".join(aux[:-1]), aux[-1]

        if len(baseNameAndParams) > 1:
            pairs = baseNameAndParams[1][1:].split("&")

            for p in pairs:
                name, value = p.split("=")
                fileName += "_" + value

        if fileExt != "":
            fileName += "." + fileExt

        return fileName


# --------------------
#  AUXILIARY METHODS
# --------------------

def toFile(name, content):
    f = open(name, "w")
    f.write(content)
    f.close()


# ------
#  MAIN
# ------

if __name__ == "__main__":
    h = Handler(sys.argv[1])
    h.sendRequests()
