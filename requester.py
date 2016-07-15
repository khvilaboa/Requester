import cookielib, urllib, urllib2, re, sys, logging, time
from abc import ABCMeta, abstractmethod

# filename='programLog.txt', 
logging.basicConfig(level=logging.DEBUG, format=' %(asctime)s - %(levelname)s - %(message)s')
#logging.disable(logging.CRITICAL)

# ---------
#  CLASSES
# ---------

class Handler:

    # Commands
    initTokens = ['INPUT']
    baseTokens = ['ID', 'URL', 'PARAMS', 'ACTION', 'TYPE']
    levelTokens = ['PRE', 'POST', 'PRE-EACH', 'POST-EACH']
    inLevelTokens = {'ALL': ['OUTPUT', 'DELAY'], 'PRE': [], 'POST': ['GETVAR', 'INVOKE']}

    # Request types
    reqTypes = ['AUTO', 'CALLABLE']

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

        try:
            self.parse()
        except SyntaxError as e:
            print "Syntax error: %s" % e

    # Check syntax and raise exceptions if needed (bad input file syntax)
    def preParse(self, content):
        #content = re.sub("\n\n+", "\n\n", content.strip())
        #requests = content.split("\n\n")
        content = content + "\n"  # Assures the last newline

        nLine = 1
        nRequest = 0
        level = "BASE"
        expectingRequest = True
        hasUrl = False
        hasCommands = False
        startingAt = 1
        reqId = None

        currBuff = ""
        outBuff = ""

        for line in content.split("\n"):
            logging.debug("%d: %s" % (nLine, line))

            # Check if the current line it's a comment
            if re.match("\s*#.*", line):
                if re.match("#\s*INIT\s*$", line):  # Initialization mark
                    if currBuff == "":
                        currBuff += "#INIT" + "\n"
                    else:
                        print "Warning: The INIT comment has to be at the beginning of the request to take effect (line %d)" % nLine
                nLine += 1
                continue

            # Blank lines means the start of a new request
            if re.match("^\s*$", line):
                if expectingRequest == False:
                    logging.debug("%d: End of request" % nLine)
                    
                    # Check semantic aspects of the last request
                    logging.debug("Has URL: %s" % hasUrl)
                    logging.debug("Has cmds: %s" % hasCommands)
                    if hasCommands and not hasUrl:
                        reqInfo = reqId if reqId is not None else "starting at %d" % startingAt
                        raise SyntaxError("Detected request without URL specified (%s)" % reqInfo)

                    # Dumps the current buffer into de output one if its content it's valid
                    if currBuff != "" and currBuff != "#INIT\n":
                        #print ">%s<" % currBuff
                        outBuff += currBuff + "\n"
                currBuff = ""
                expectingRequest = True
                nLine += 1
                continue

            # Check correct syntax ('TOKEN: VALUE')
            expr = "\t?([\w-]*)\s*:\s*([^\s]*)\s*"
            correctLine = re.match(expr, line, re.I)

            if not correctLine:
                raise SyntaxError("Invalid syntax in (line %d)" % (nLine))

            # Check indent in base level
            if level == "BASE" and line.startswith("\t"):
                raise SyntaxError("Unexpected indent (line %s)" % nLine)
            elif not line.startswith("\t"):
                level = "BASE"

            # Inits a new request after a new line (or several)
            if expectingRequest:
                logging.debug("%d: New request" % nLine)

                # Reset control variables
                expectingRequest = False
                level = "BASE"
                hasUrl = False
                hasCommands = False
                startingAt = nLine
                reqId = None
                nRequest += 1

            # Get the token and its value
            token, value = correctLine.groups()
            token = token.upper()

            if level == "BASE":
                if token in self.levelTokens:
                    level = token
                    hasCommands = True

                elif token not in self.baseTokens:
                    raise SyntaxError("Token %s not recognized in 'BASE' level (line %d)" % (token, nLine))

                elif token == "URL":
                    hasUrl = True
                elif token == "ID":
                    reqId = value
                elif token == "TYPE":
                    value = value.upper()
                    if value not in self.reqTypes:
                        raise SyntaxError("'%s' is not a valid type of request (line %d))" % (value, nLine))

                hasCommands = True

            elif level in self.levelTokens:
                key = level if "-" not in level else level[:level.find("-")] # [EV]-EACH -> [EV]
                if token not in self.inLevelTokens[key] and token not in self.inLevelTokens['ALL']:
                    raise SyntaxError("Token %s not recognized in %s level (line %d)" % (token, level, nLine))

                if token == "INVOKE" and not re.search("ID\s*:\s*%s\s*$" % value, content, re.M):
                    logging.debug("ExprInvoke: %s" % ("ID\s*:\s*%s\s*$" % value))
                    raise SyntaxError("There isn't a request with ID '%s' (line %d)" % (value, nLine))
                elif token == "DELAY":
                    if not re.match("^[\d]*(.[\d]+)?( ?(ms|s))?$", value):
                        raise SyntaxError("Incorrect parameters in the DELAY command (line %d)" % nLine)
            currBuff += line + "\n"
            nLine += 1

        #print ">>>%s<<<" % outBuff.strip()

        return outBuff.strip()

    # Load the data of the file specified
    def parse(self):
        logging.debug('Loading input file data...')
        f = open(self.fileName, "r")
        content = f.read()
        f.close()

        # Check syntax errors
        content = self.preParse(content)

        self.requests = []

        # For each requests in the requests file (separated by a blank line)
        for reqLines in content.split("\n\n"):
            req = self.parseRequest(reqLines)
            if req: 
                self.requests.append(req)

    def translateGlobals(self, line):
        #bug('Globals: %s', str(self.inputs))
        for k, v in self.inputs.iteritems():
            line = line.replace("[[" + k + "]]", v)
        #logging.debug('Translated: %s', line)
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
                    #logging.debug('Comment detected...%s' % line)
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
            eventActions = {}
            reqType = "AUTO"

            level = "base"

            for line in lines:

                if self.isComment(line): # comment
                    #logging.debug('Comment detected...%s' % line)
                    continue

                # Get and format name and value of the command (ex: "METHOD : GET")
                logging.debug("Reading line... (%s). Level: %s" % (line, level))
                events = ("pre", "post", "pre-each", "post-each")
                if level in events:
                    if line.startswith("\t"):
                        logging.debug("Adding %s action... (%s -> %s)" % (level, name, value))
                        if level in eventActions:
                            eventActions[level] += line[1:] + "\n"
                        else:
                            eventActions[level] = line[1:] + "\n"
                        continue
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
                    elif name == "PRE-EACH":
                        level = "pre-each"
                    elif name == "POST-EACH":
                        level = "post-each"
                    else:
                        pass # TODO: raise exception 

            if url == "":
                return # TODO: raise exception

            logging.debug("Event actions... (%s)" % eventActions)

            return RequestGroup(self, reqId, method, url, params, action, reqType, eventActions)

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
    def __init__(self, parent, reqId, method, url, params, action, reqType, eventActions):
        self.parent = parent
        self.id = reqId
        self.url = url
        self.method = method
        self.params = params
        self.action = action
        self.type = reqType
        self.eventActions = eventActions

        self.uniqueId = 0

        # To store the url and params of the next request
        self.parsedUrl = self.url
        #self.parsedParams = self.params
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
        logging.debug("EXECUTING REQUEST")

        sources = self.extractSources()
        logging.debug("Sources: %s" % sources)
        
        if "pre" in self.eventActions:
            logging.debug("Executing preActions...")
            self.executeEventActions("pre")

        if sources:
            for comb in SourceHandler(sources.values()):

                # Fill sources variables
                for src in sources.values():
                    if src.destVar != None:
                        self.locals[src.destVar] = src.lastValue

                if "pre-each" in self.eventActions:
                    logging.debug("Executing preEachActions...")
                    self.executeEventActions("pre-each")

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

                if "post-each" in self.eventActions:
                    logging.debug("Executing postEachActions...")
                    self.executeEventActions("post-each")

                # Remove the request-dependent information of the local variables 
                del self.locals["code"]
        else:
            if self.action != None:
                logging.debug("Executing main action (download)...")
                urlWithParams = self.getUrlWithParams()
                self.action.setUrl(urlWithParams)
                self.action.execute()
            else:
                logging.debug("Executing main action (request)...")
                self.parsedUrl = self.parent.translateGlobals(self.parsedUrl)
                self.send()

        if "post" in self.eventActions:
            logging.debug("Executing postActions...")
            self.executeEventActions("post")

    def translateLocals(self, s):
        #logging.debug('Locals: %s', str(self.locals))
        for k, v in self.locals.iteritems():
            s = s.replace("[[" + k + "]]", v)
        #logging.debug('Translated (locals): %s', s)
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
        self.url, newSources = self.getSources(self.url)
        sources.update(newSources)

        if self.params != None:
            self.params, newSources = self.getSources(self.params)
            sources.update(newSources)

            """for k, v in self.params.iteritems():
                # Check if are special commands in the key
                spec, src = self.getSourceFromCmd(k)
                sources.update(newSources)

                # Check if are special commands in the value
                spec, src = self.getSourceFromCmd(v)
                sources.update(newSources)"""

        return sources

    def getSources(self, line):
        matches = re.findall("(\[\[(\w*)\:([\w,]*)(->(\w*))?\]\])", line)
        sources = {}

        for mData in matches:
            match, name, params, _, var = mData

            if name == "FILE":
                fileName = params
                src = FileSource(fileName)
            elif name == "SEQ":
                seq = params
                src = SeqSource(seq)

            if var:
                src.destVar = var

            newSourceId = "[[SRC%d]]" % self.getUniqueId()
            print type(mData), match
            line = line.replace(match, newSourceId, 1)
            sources[newSourceId] = src

        logging.debug(matches)
        logging.debug(sources)
        logging.debug(line)

        return line, sources


    def getUniqueId(self):
        currId = self.uniqueId
        self.uniqueId += 1
        return currId

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
    def executeEventActions(self, event):

        for action in self.eventActions[event].split("\n"):

            # Translate vars
            action = self.parent.translateGlobals(action)
            action = self.translateLocals(action)

            # Get command and its info
            name, value = self.getPair(action, ":")
            name = name.strip().upper()
            value = value.strip()

            # Execute the command
            if name == "OUTPUT":
                print value
            elif name == "DELAY":
                num, _, unit = re.search("([\d.]*)( ?(ms|s))?", "2000 ms").groups()
                numSec = float(num) / (1 if unit == "s" else 1000)
                time.sleep(numSec)

            if event.startswith("post"):  # Only post-actions
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
        self.destVar = None
        self.lastValue = None
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

        if self.pointer < len(self.data):
            val = self.data[self.pointer]
            self.pointer += 1
            self.lastValue = val
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
            val = str(self.pointer)
            self.pointer += self.step
            self.lastValue = val
            return val
        else:
            raise StopIteration()

    def reset(self):
        self.pointer = self.ini - self.step


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
    h = Handler("req\\local.req") #sys.argv[1]
    h.sendRequests()
