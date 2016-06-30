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
                                           urllib2.HTTPHandler(debuglevel=0))
        urllib2.install_opener(self.opener)

        self.inputs = {}  # Global inputs
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

    def translateGlobals(self, line):
        logging.debug('Globals: %s', str(self.inputs))
        for k, v in self.inputs.iteritems():
            line = line.replace("[[" + k + "]]", v)
        logging.debug('Translated: %s', line)
        return line

    def isComment(self, line):
        return bool(re.match("^\s*#", line))

    # Returns a Request obj. from the lines in which a expression is defined
    def parseRequest(self, req):

        # Replace items related to the global inputs
        lines = req.split("\n")

        # The data to parse corresponds with the initialization configuration
        if lines and lines[0].replace(" ", "").upper() == "#INIT": 
            logging.debug('INITIALIZING')
            self.inputs = {}

            for line in lines:

                if self.isComment(line): # comment
                    logging.debug('Comment detected...%s' % line)
                    continue

                name, value = self.getPair(line, ":")
                name = name.strip().upper()

                if name == "INPUT":
                    for k in value.replace(" ", "").split(","):
                        self.inputs[k] = raw_input(k + ": ")
        else:
            logging.debug("PARSING NEW REQUEST")
            reqId = None
            method = "GET"
            url = ""
            params = None
            action = None
            preActions = ""
            postActions = ""
            reqType = "AUTO"

            level = "base"

            for line in lines:

                if self.isComment(line): # comment
                    logging.debug('Comment detected...%s' % line)
                    continue

                # Get and format name and value of the command (ex: "METHOD : GET")
                logging.debug("Reading line... (%s)" % line)

                if level == "pre":
                    if line.startswith("\t"):
                        logging.debug("Adding preaction... (%s -> %s)" % (name, value))
                        preActions += line[1:] + "\n"
                    else:
                        level = "base"
                if level == "post":
                    if line.startswith("\t"):
                        logging.debug("Adding postaction... (%s -> %s)" % (name, value))
                        postActions += line[1:] + "\n"
                    else:
                        level = "base"        

                if level == "base":

                    line = self.translateGlobals(line)

                    name, value = self.getPair(line, ":")
                    name = name.strip().upper()
                    value = value.strip()

                    if name == "ID":
                        reqId = value.upper()
                    elif name == "URL":
                        url = value
                    elif name == "METHOD":
                        method = value.upper()
                    elif name == "PARAMS":
                        params = self.parseParams(value)
                    elif name == "ACTION":
                        logging.debug("Establishing download action...")
                        action = DownloadAction(url)
                    elif name == "TYPE":
                        reqType = value.upper()
                    elif name == "PRE":
                        level = "pre"
                    elif name == "POST":
                        level = "post"
                    else:
                        pass # TODO: raise exception 

            if url == "":
                return # TODO: raise exception
            logging.debug("Preactions... (%s)" % preActions)
            logging.debug("Postactions... (%s)" % postActions)

            return RequestGroup(self, reqId, method, url, params, action, reqType, preActions, postActions)

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
            if req.type == "AUTO":
                req.execute()
            else:
                logging.debug("Skipping request... (%s)" % req.type)

    def getInputs(self):
        return self.inputs

    def executeById(self, reqId):
        for req in self.requests:
            if req.id is not None and req.id.upper() == reqId.upper():
                req.execute()
                return True
        return False


# Identifies a group of related requests
class RequestGroup:
    def __init__(self, parent, reqId, method, url, params, action, reqType, preActions, postActions):
        self.parent = parent
        self.id = reqId
        self.url = url
        self.method = method
        self.params = params
        self.action = action
        self.type = reqType
        self.preActions = preActions
        self.postActions = postActions

        # To store the url and params of the next request
        self.parsedUrl = self.url
        self.parsedParams = urllib.urlencode(self.params) if params != None else None

        self.locals = {}

    def __str__(self):
        toRet = "%s %s" % (self.method, self.parsedUrl)

        if self.method == "GET" and self.parsedParams:
            toRet += "?%s" % self.parsedParams
        elif self.method == "POST":
            toRet += "\nData: %s" % self.parsedParams

        return toRet

    def getUrlWithParams(self):
        urlWithParams = self.url + ("?" + self.getParamsStr() if self.params else "")
        urlWithParams = self.parent.translateGlobals(urlWithParams)

        if urlWithParams.startswith("//"):
            urlWithParams = "http://" + urlWithParams[2:]
        return urlWithParams

    def getUrlAndParams(self):
        return

    def execute(self):
        print
        logging.debug("EXECUTING REQUEST")

        sources = self.extractSources()
        logging.debug("Sources: %s" % sources)

        logging.debug("Executing preActions...")
        if self.preActions:
            #self.preActions = self.parent.translateGlobals(self.preActions)
            self.executeEventActions(self.preActions, "pre")

        if sources:
            for comb in SourceHandler(sources.values()):
                urlWithParams = self.getUrlWithParams()

                # Replace the data given in the sources in the url and params
                for k, v in zip(sources.keys(), comb):
                    urlWithParams = urlWithParams.replace(k, v)

                self.parsedUrl, self.parsedParams = self.getPair(urlWithParams, "?")

                logging.debug("Request details:")
                logging.debug(self)

                if self.action != None:
                    logging.debug("Executing main action (download)...")
                    self.action.setUrl(urlWithParams)
                    self.action.execute()
                else:
                    logging.debug("Executing main action (request)...")
                    self.parsedUrl = self.parent.translateGlobals(self.parsedUrl)
                    self.send()
        else:
            if self.action != None:
                urlWithParams = self.getUrlWithParams()
                self.action.setUrl(urlWithParams)
                self.action.execute()
            else:
                logging.debug("Executing main action (request)...")
                self.parsedUrl = self.parent.translateGlobals(self.parsedUrl)
                self.send()

        logging.debug("Executing postActions...")
        if self.postActions:
            #self.postActions = self.parent.translateGlobals(self.postActions)
            #self.postActions = self.translateLocals(self.postActions)
            self.executeEventActions(self.postActions, "post")

    def translateLocals(self, s):
        #logging.debug('Locals: %s', str(self.locals))
        for k, v in self.locals.iteritems():
            s = s.replace("[[" + k + "]]", v)
        logging.debug('Translated (locals): %s', s)
        return s

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

        logging.debug("Requested url: %s", url)

        if self.method == "GET":
            if self.parsedParams: url += "?" + self.parsedParams
            self.locals["code"] = urllib2.urlopen(url).read()
        elif self.method == "POST":
            self.locals["code"] = urllib2.urlopen(url, urllib.urlencode(self.parsedParams)).read()


    # Separate name and value in a expression of the form: "NAME SEP VALUE"
    def getPair(self, pair, sep):
        tmp = pair.split(sep)
        name, value = tmp[0], sep.join(tmp[1:])
        return name.strip(), value.strip()


    # Parse and execute the actions related with events ('pre', 'post')
    def executeEventActions(self, actions, event):

        for action in actions.split("\n"):

            # Translate vars
            action = self.parent.translateGlobals(action)
            if event == "post":
                action = self.translateLocals(action)

            # Get command and its info
            name, value = self.getPair(action, ":")
            name = name.strip().upper()
            value = value.strip()

            # Execute the command
            if name == "OUTPUT":
                print value

            if event == "post":  # Only post-actions
                if name == "GETVAR":
                    logging.debug("Getting the var (%s)", value)
                    if "code" in self.locals:
                        varName, expr = self.getPair(value, ",")
                        logging.debug("Var: %s, expr: >%s<", varName, expr)
                        #logging.debug("Code: %s", self.locals["code"])
                        reRes = re.search(expr, self.locals["code"])

                        if reRes:
                            self.parent.inputs[varName] = reRes.group(0) if len(reRes.groups()) == 0 else reRes.group(1) 
                            logging.debug("Result: %s", self.parent.inputs[varName])
                elif name == "INVOKE":
                    # Invoke a callable requesT by ID
                    logging.debug("INVOKE: Trying to execute the request with ID '%s'..." % value)
                    executed = self.parent.executeById(value)

                    if executed:
                        logging.debug("INVOKE: Executed correctly")
                    else:
                        logging.debug("INVOKE: ID not found")


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

    def __init__(self, url, condition = True):  # self or external url
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
            logging.debug("Downloading... (%s). Filename: %s" % (self.url, self.getFileName()))
            urllib.urlretrieve(self.url, self.getFileName())
        else:
            logging.debug(">>> Condition not accomplished <<<")

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
    h = Handler("req\\test.req") #sys.argv[1]
    h.sendRequests()
