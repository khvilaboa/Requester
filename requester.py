import cookielib, urllib, urllib2, re, sys, logging, time
from abc import ABCMeta, abstractmethod
from collections import OrderedDict

# filename='programLog.txt', 
logging.basicConfig(level=logging.DEBUG, format=' %(asctime)s - %(levelname)s - %(message)s')
logging.disable(logging.CRITICAL)

# ---------
#  CLASSES
# ---------

class Handler:

	# Commands
	initTokens = ['INPUT']
	baseTokens = ['ID', 'URL', 'PARAMS', 'ACTION', 'TYPE']
	levelTokens = ['PRE', 'POST', 'PRE-EACH', 'POST-EACH']
	inLevelTokens = {'ALL': ['OUTPUT', 'DELAY', 'END'], 'PRE': [], 'POST': ['GETVAR', 'INVOKE']}

	# Request types
	reqTypes = ['AUTO', 'CALLABLE']
	reqActions = ['REQUEST', 'DOWNLOAD']
	reqEnds = ['ITER', 'REQUEST', 'SCRIPT']

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
		self.requests = OrderedDict()
		self.invRequests = {}  # Invoke requests

		try:
			self.parse()
		except SyntaxError as e:
			print "Syntax error: %s" % e
			sys.exit(0)
			
	# Load the data of the file specified
	def parse(self):
		def addRequest(id, url, method, params, action, type, inLevelData):
			if url == None:
				raise SyntaxError("\nRequest starting at line %d: 'URL' not found.\n" % reqStartLine)
			if type == "AUTO":
				self.requests[id] = (url, method, params, action, inLevelData)
			elif type == "CALLABLE":
				self.invRequests[id] = (url, method, params, action, inLevelData)
			print "->", type, (url, method, params, action, inLevelData)
			
		logging.debug('Loading input file data...')
		f = open(self.fileName, "r")
		content = f.read()
		f.close()

		# Parsed data
		inLevelData = {}  # For store the commands of the events (PRE, POST...)
		
		# Parsing vars
		numLine = 0
		reqStartLine = 1
		numRequest = 0
		
		lastLevel = 0
		curLevel = 0
		curLevelName = None
		expectIncLevel = False
		
		newRequest = True
		initRequest = False
		hasRequest = False  # For the last verification
		
		for inputLine in content.split("\n"):
			numLine += 1
			print "---%s---" % inputLine
			
			# Check if it's the initial (configuration) region 
			if re.match("^/s*# ?INIT/s*$", inputLine):
				if numRequest != 0:
					raise SyntaxError("\nLine %d: Init configurations must be at the beginning of the script.\n" % numLine)
				initRequest = True
				continue
			
			# Check if it's a comment
			if re.match("^[ \t]*#.*$", inputLine):
				continue
			
			# Init configurations
			if initRequest:
				atrName, atrValue = self.getPair(inputLine, ":")
				atrName = atrName.upper()
				
				if atrName not in self.initTokens:
					raise SyntaxError("\nLine %d: Attribute '%s' not recognized in the init region.\n" % (numLine, atrName))
				
				if atrName == "INPUT":
					for k in atrValue.replace(" ", "").split(","):
						self.inputs[k] = raw_input(k + ": ")
			
			# Check if it's a blank line (points the start of a new request)
			if re.match("^[ \t]*$", inputLine):
				newRequest = True
				continue
				
			# If comes a new request save the previous one and reset the variables
			if newRequest:
				# Check that there were more requests
				if numRequest != 0:
					addRequest(id, url, method, params, action, type, inLevelData)
					
				# Reset request values
				newRequest = False
				id = "_REQ%d" % numRequest
				url = None
				method = "GET"
				params = None
				action = "REQUEST"
				type = "AUTO"
				inLevelData = {}
				reqStartLine = numLine
				
				numRequest += 1
				
			# Get attribute name and value
			atrName, atrValue = self.getPair(inputLine, ":")
			atrName = atrName.upper()

			# Determine the level of indentation (based on tabs)
			curLevel = len(re.search("^(\t*)", inputLine).group(1))
			
			# Starts an event region
			if curLevel == 0 and atrName in self.levelTokens:
				if atrValue != "":
					raise SyntaxError("\nLine %d: %s doesn't expect a value.\n" % (numLine, atrName))
				
				lastLevel = curLevel
				curLevelName = atrName
				
				if curLevelName in inLevelData:
					raise SyntaxError("\nLine %d: %s was already defined.\n" % (numLine, atrName))
				
				inLevelData[curLevelName] = []
				continue
			elif expectIncLevel and curLevel-lastLevel != 1:
				raise SyntaxError("\nLine %d: Indentation error.\n" % numLine)
			elif curLevel > 0:
				# X-EACH -> X
				genLevelName = curLevelName if not "-" in curLevelName else curLevelName[:curLevelName.find("-")]
				
				if atrName not in self.inLevelTokens[genLevelName] and atrName not in self.inLevelTokens["ALL"]:
					raise SyntaxError("\nLine %d: Unrecognized attribute (%s).\n" % (numLine, atrName))
				
				# Specific filters
				if atrName == "DELAY" and not re.match("^[\d]*(.[\d]+)?( ?(ms|s))?$", atrValue):
					raise SyntaxError("\nLine %d: Unexpected DELAY value" % numLine)
				if atrName == "END":
					if atrValue.upper() not in self.reqEnds:
						raise SyntaxError("\nLine %d: 'END' must be ITER, REQUEST OR SCRIPT.\n" % numLine)
					if atrValue == "ITER" and not curLevelName.upper().endswith("-EACH"):
						raise SyntaxError("\nLine %d: 'END: ITER' is only allowed in 'PRE-EACH' and 'POST-EACH' events" % numLine)
				inLevelData[curLevelName].append((atrName, atrValue))
				continue
				
			hasRequest = True
			
			if atrName == "ID":
				id = atrValue.upper()
				if id.startswith("_REQ"):
					raise SyntaxError("\nLine %d: Identifiers starting with '_REQ' are reserved.\n" % numLine)
			elif atrName == "URL":
				url = atrValue
			elif atrName == "METHOD":
				method = atrValue.upper()
			elif atrName == "PARAMS":
				params = atrValue
			elif atrName == "TYPE":
				if atrValue.upper() not in self.reqTypes:
					raise SyntaxError("\nLine %d: Request type must be AUTO or INVOKE.\n" % numLine)
				type = atrValue.upper()
			elif atrName == "ACTION":
				if atrValue.upper() not in self.reqActions:
					raise SyntaxError("\nLine %d: Action must be REQUEST or DOWNLOAD.\n" % numLine)
				action = atrValue.upper()
			else:
				raise SyntaxError("\nLine %d: Attribute '%s' not recognized.\n" % (numLine, atrName))
			
		
		if hasRequest:
			addRequest(id, url, method, params, action, type, inLevelData)

	def translateGlobals(self, line):
		#bug('Globals: %s', str(self.inputs))
		for k, v in self.inputs.iteritems():
			line = line.replace("[[" + k + "]]", v)
		#logging.debug('Translated: %s', line)
		return line

	# Separate name and value in a expression of the form: "NAME SEP VALUE"
	def getPair(self, pair, sep):
		tmp = pair.split(sep)
		name, value = tmp[0], sep.join(tmp[1:])
		return name.strip(), value.strip()

	def sendRequests(self):
		for req in self.requests:
			print "Executing: ", req
			self.executeRequest(*self.requests[req])

	def getInputs(self):
		return self.inputs

	def executeById(self, reqId):
		for req in self.invRequests:
			if req.upper() == reqId.upper():
				self.executeRequest(*self.invRequests[req])

	def executeRequest(self, url, method, params, action, inLevelData, locals = {}):
		r = RequestGroup(self, url, method, params, action, inLevelData)
	
		try:
			r.execute()
		except StandardError as e:
			if str(e) != "END_REQUEST":
				print e, type(e)
				raise StandardError(e)

# Identifies a group of related requests
class RequestGroup:
	def __init__(self, parent, url, method, params, action, eventActions, locals = {}):
		self.parent = parent
		self.url = url
		self.method = method
		self.params = params
		self.action = action
		self.eventActions = eventActions
		self.locals = locals
		
		self.uniqueId = 0  # For generate unique sequence names

		# To store the url and params of the next request
		self.parsedUrl = self.url
		#self.parsedParams = self.params
		self.parsedParams = self.params
		
	def execute(self):
		sources = self.extractSources()
		logging.debug("Sources: %s" % sources)
		
		if "PRE" in self.eventActions:
			logging.debug("Executing preActions...")
			self.executeEventActions("PRE")

		if sources:
			for comb in SourceHandler(sources.values()):
				# Fill sources variables
				for src in sources.values():
					if src.destVar != None:
						self.locals[src.destVar] = src.lastValue
		
				try:
					if "PRE-EACH" in self.eventActions:
						logging.debug("Executing preEachActions...")
						self.executeEventActions("PRE-EACH")

					urlWithParams = self.getUrlWithParams()

					# Replace the data given in the sources in the url and params
					for k, v in zip(sources.keys(), comb):
						urlWithParams = urlWithParams.replace(k, v)

					self.parsedUrl, self.parsedParams = self.getPair(urlWithParams, "?")

					logging.debug("Request details:")
					logging.debug(self)

					if self.action == "DOWNLOAD":
						logging.debug("Executing action (download)...")
						downAction = DownloadAction(urlWithParams)
						downAction.execute()
					else:
						logging.debug("Executing main action (request)...")
						self.parsedUrl = self.translateLocals(self.parent.translateGlobals(self.parsedUrl))
						self.send()

					if "POST-EACH" in self.eventActions:
						logging.debug("Executing postEachActions...")
						self.executeEventActions("POST-EACH")
				except StandardError as e:
					if str(e) != "END_ITER":
						raise StandardError(e)
				finally:
					# Remove the request-dependent information of the local variables 
					if "code" in self.locals:
						del self.locals["code"]
		else:
			if self.action == "DOWNLOAD":
				logging.debug("Executing action (download)...")
				urlWithParams = self.getUrlWithParams()
				downAction = DownloadAction(urlWithParams)
				downAction.execute()
			else:
				logging.debug("Executing main action (request)...")
				self.parsedUrl = self.translateLocals(self.parent.translateGlobals(self.parsedUrl))
				self.send()

		if "POST" in self.eventActions:
			logging.debug("Executing postActions...")
			self.executeEventActions("POST")
		
	def getUrlWithParams(self):
		urlWithParams = self.translateLocals(self.parent.translateGlobals(self.url))
		
		if self.params:
			urlWithParams += "?" + self.translateLocals(self.parent.translateGlobals(self.params))

		if urlWithParams.startswith("//"):  # TODO
			urlWithParams = "http://" + urlWithParams[2:]
			
		return urlWithParams
		
	# Send the current request
	def send(self):
		url = self.parsedUrl

		logging.debug("Requested url: %s", url)
		print ">%s<" % url

		if self.method == "GET":
			if self.parsedParams: url += "?" + self.parsedParams
			self.locals["code"] = urllib2.urlopen(url).read()
		elif self.method == "POST":
			self.locals["code"] = urllib2.urlopen(url, self.parsedParams).read()
			
	# ------------------------------------------------------------------
			
	# Identifies and returns the needed sources related to the request group
	def extractSources(self):
		# Check if are sources in the url
		self.url, sources = self.getSources(self.url)
		
		# Check if are sources in the params
		if self.params != None:
			self.params, newSources = self.getSources(self.params)
			sources.update(newSources)

		return sources

	# Auxiliar function that instances a source given it specification
	def getSources(self, line):
		matches = re.findall("(\[\[(\w*)\:([\w,]*)(->(\w*))?\]\])", line)
		sources = {}

		for mData in matches:
			match, name, params, _, var = mData
			
			if name == "FILE":
				fileName = params
				src = FileSource(fileName, var)
			elif name == "SEQ":
				seq = params
				src = SeqSource(seq, var)

			newSourceId = self.getUniqueId()
			line = line.replace(match, newSourceId, 1)
			sources[newSourceId] = src

		return line, sources
	
	# Returns a unique identifier (in the current request)
	def getUniqueId(self):
		currId = self.uniqueId
		self.uniqueId += 1
		return "[[_SRC%d]]" % currId
		
	# ------------------------------------------------------------------
		
	# Parse and execute the actions related with events ('pre', 'post'...)
	def executeEventActions(self, event):

		for action in self.eventActions[event]:

			name, value = action
			name = name.upper()
			value = value.upper()
			
			# Translate the value
			value = self.parent.translateGlobals(value)
			value = self.translateLocals(value)

			# Execute the command
			if name == "OUTPUT":
				print value
			elif name == "DELAY":
				num, _, unit = re.search("([\d.]+)( ?(ms|s))?", value).groups()
				numSec = float(num) / (1 if unit == "s" else 1000)
				time.sleep(numSec)
			elif name == "END":
				if value == "SCRIPT":
					sys.exit(0)
				else:
					raise StandardError("END_%s" % value)

			if event.startswith("POST"):  # Only post-actions
				if name == "GETVAR":
					if "code" in self.locals:
						varName, expr = self.getPair(value, ",")
						reRes = re.search(expr, self.locals["code"])
						
						logging.debug("Var: %s, expr: >%s<", varName, expr)

						if reRes:
							self.parent.inputs[varName] = reRes.group(0) if len(reRes.groups()) == 0 else reRes.group(1) 
							logging.debug("Result: %s", self.parent.inputs[varName])
				elif name == "INVOKE":
					# Invoke a callable requesT by ID
					logging.debug("INVOKE: Trying to execute the request with ID '%s'..." % value)
					executed = self.parent.executeById(value)

	
	def translateLocals(self, s):
		for k, v in self.locals.iteritems():
			s = s.replace("[[" + k + "]]", v)
		return s
	
	# ------------------------------------------------------------------
	
	def __str__(self):
		toRet = "%s %s" % (self.method, self.parsedUrl)

		if self.method == "GET" and self.parsedParams:
			toRet += "?%s" % self.parsedParams
		elif self.method == "POST":
			toRet += "\nData: %s" % self.parsedParams

		return toRet

	# ------------------------------------------------------------------

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
		self.destVar = None
		self.lastValue = None
		return self

	@abstractmethod
	def next(self): pass

	@abstractmethod
	def reset(self): pass


# Iterate over the lines of a file
class FileSource(Source):
	def __init__(self, fileName, var = None):
		self.fileName = fileName
		self.data = None
		self.pointer = 0
		self.destVar = var

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

	def __init__(self, strDef, var = None):
		try:
			params = map(lambda x: int(x), strDef.split(","))
			if len(params) != 3: raise SyntaxError

			self.ini, self.fin, self.step = params
			self.pointer = self.ini #- self.step
		except SyntaxError:
			raise SyntaxError("Secuencia no valida")
			
		self.destVar = var

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

# Parent for all the actions
class Action:
	__metaclass__ = ABCMeta

	def __init__(self, url):  # , condition = True
		self.url = url
		#self.condition = condition

	"""@abstractmethod
	def conditionAccomplished(self): pass"""

	@abstractmethod
	def execute(self): pass

	def setUrl(self, url):
		self.url = url


class DownloadAction(Action):

	"""def conditionAccomplished(self):
		if self.condition:
			return True
		else:
			return False # TODO"""

	def execute(self):
		#if self.conditionAccomplished():
		logging.debug("Downloading... (%s). Filename: %s" % (self.url, self.getFileName()))
		urllib.urlretrieve(self.url, self.getFileName())
		#else:
		#	logging.debug(">>> Condition not accomplished <<<")

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
	h = Handler(sys.argv[1]) #sys.argv[1]
	h.sendRequests()
