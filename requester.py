import cookielib, urllib, urllib2, re, sys
from abc import ABCMeta, abstractmethod

# ---------
#  CLASSES
# ---------

class Handler:
    def __init__(self, fileName):
        self.fileName = fileName
        self.requests = []

        # Create opener with cookie support
        self.cookiejar = cookielib.CookieJar()
        self.opener = urllib2.build_opener(urllib2.HTTPCookieProcessor(self.cookiejar),
                                           urllib2.HTTPHandler(debuglevel=1))
        urllib2.install_opener(self.opener)

        self.parse()

    def parse(self):
        f = open(self.fileName, "r")
        content = f.read()
        f.close()

        self.requests = []

        # For each requests in the requests file (separated by a blank line)
        for reqLines in content.split("\n\n"):
            req = self.parseRequest(reqLines)
            if req: self.requests.append(req)

    # Returns a Request obj. from the lines in which a expression is defined
    def parseRequest(self, req):
        lines = req.split("\n")

        method = "GET"
        url = ""
        params = None

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

        return RequestGroup(method, url, params) if url <> "" else None

    # Returns the params (in dictionary form) from the line that specifies them
    def parseParams(self, params_line):
        params = {}

        for param in params_line.split("&"):
            name, value = self.getPair(param, "=")

            match = re.match(r"\[\[(.*)\]\]", value)
            if match:  # Special commands
                sc_spec = self.getPair(match.group(1), ":")
                sc_name = sc_spec[0].upper()
                sc_params = sc_spec[1:]

                if sc_name == "FILE":  # TODO: Check if file exists
                    fileName = sc_params[0]
                    params[name] = FileSource(fileName)
                elif sc_name == "SEQ":
                    seq = sc_params[0]
                    params[name] = SeqSource(seq)
                else:
                    pass  # TODO: raise Exception
            else:
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


# Identifies a group of related requests
class RequestGroup:
    def __init__(self, method, url, params):
        self.url = url
        self.method = method
        self.params = params

    def __str__(self):
        toRet = ""
        toRet += "%s %s" % (self.method, self.url)

        if self.method == "GET" and len(self.params) <> 0:
            toRet += "?%s" % urllib.urlencode(self.params)
        elif self.method == "POST":
            toRet += "\nData: %s" % self.params

        return toRet

    def execute(self):
        print "Time to execute.."
        print self
        print "sources: ", self.extractSources()
        print ""

        keys, sources = self.extractSources()
        if sources:
            print keys, sources
            for comb in SourceHandler(sources):
                for k, v in zip(keys, comb):
                    self.params[k] = v

                print self
                content = self.send()
            # TODO: insert conditional actions
        else:
            content = self.send()
            print "\nLogged in: " + str(not "Log in" in content)
            toFile("content.html", content)

        # content = urllib2.urlopen(*self.getData()).read()

    def extractSources(self):
        keys = []
        sources = []
        for k, v in self.params.iteritems():
            if not isinstance(v, str):
                keys.append(k)
                sources.append(v)

        return keys, sources

    # Return either "URL[?params]" if it's a GET request or ["URL", params] if it's post
    def send(self):
        url = self.url
        if self.method == "GET":
            if len(self.params) <> 0:
                url += "?" + urllib.urlencode(self.params)
            return urllib2.urlopen(url).read()
        elif self.method == "POST":
            return urllib2.urlopen(url, urllib.urlencode(self.params)).read()


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
            if len(params) <> 3: raise SyntaxError

            self.ini, self.fin, self.step = params
            self.pointer = self.ini - self.step
        except SyntaxError:
            raise SyntaxError("Secuencia no valida")

    def next(self):
        if self.pointer < self.fin:
            self.pointer += self.step
            return self.pointer
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
