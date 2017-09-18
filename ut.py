#!/usr/bin/python3

from bs4 import BeautifulSoup
from urllib.request import urlopen, Request
import re, sys, os, getopt, time, pprint, datetime, base64

class UT(object):
	"""docstring for UT"""

	verbose = False
	quiet = False
	extended = False
	domain = ""
	starturl = None
	secured = False
	logfile = None
	domain = ''
	action = 'scan'
	only_static = False
	external_static = False
	list_view = False
	recursive = 0
	static_extensions = ['jpg','png','pdf','jpeg','mp3','mp4','gif','eps','exe','dmg','zip','tar','gz','deb','rpm']
	noreferrer = False

	def read_params(self,mainargs):
		try:
			opts, args = getopt.getopt(mainargs, "hvqer:", ["help","verbose","quiet","secured","diff","only-static","external-static","list","no-ref"])
		except getopt.GetoptError as err:
			print(err)
			sys.exit(2)

		for o, a in opts:
			if o in ("-h", "--help"):
				print("Help text coming soon")
				sys.exit()

			elif o in ("-v", "--verbose"):
				self.verbose = True
			elif o in ("-q", "--quiet"):
				self.quiet = True
			elif o in ("-e"):
				self.extended = True
			elif o in ("--secured"):
				self.secured = True
			elif o in ("-r"):
				self.recursive = int(a)
			elif o in ("--only-static"):
				self.only_static = True
			elif o in ("--external-static"):
				self.external_static = True
			elif o in ("--list"):
				self.list_view = True
			elif o in ("--no-ref"):
				self.noreferrer = True

			elif o in ("--diff"):
				self.action = "diff"
			else:
				assert False, "unhandled option"

		if self.action == "scan":
			if len(args) > 0:
				self.domain = args[0]
				if len(args) > 1:
					self.starturl = args[1]
			else:
				assert False, "wrong input parameters"
		elif self.action == "diff":
			if len(args) > 0:
				self.url = args[0]
		else:
			assert False, "unhandled action"

		global workdir
		workdir = str(os.path.expanduser("~")) + "/.ut/"
		try:
			os.stat(workdir)
		except:
			os.mkdir(workdir)

	def __init__(self, mainargs):
		try:
			self.read_params(mainargs)

			if self.action == "scan":
				self.scan()
			elif self.action == "diff":
				self.diff()
			else:
				assert False, "unhandled action"
		except SystemExit:
			pass
		except Exception as e:
			raise e
			print(e)

	def log(self,msg=[""],display_it = True):
		if display_it:
			print("\t".join(msg))
		self.logfile.write("\t".join(msg) + "\n")

	def suredir(self,directory):
		try:
			os.stat(directory)
		except:
			os.mkdir(directory)	   

	def scan(self):
		global workdir, cachedir, domaindir

		domaindir = workdir + self.domain + "/"
		self.suredir(domaindir)

		cachedir = workdir + self.domain + "/cache/"
		self.suredir(cachedir)

		self.datesuffix = base64.b64encode(time.strftime("%Y-%m-%d %H:%M:%S").encode("ascii"))

		if self.secured:
			self.homeurl = "https://" + self.domain + "/"
		else:
			self.homeurl = "http://" + self.domain + "/"

		if self.starturl is None:
			self.starturl = self.homeurl

		self.visited = []
		self.visited_external = []
		self.successful = 0
		self.skipped = 0
		self.errored = 0
		self.warned = 0
		self.recursive_counter = 0

		self.logfile = open(domaindir + time.strftime("%Y%m%d%H%M%S") + ".log","w")
		if not self.list_view:
			self.log(["Domain:",self.domain])
			self.log()

		try:
			self.chain(self.starturl)
		except KeyboardInterrupt:
			self.log()
			self.log(["Operation Aborted"])
		except:
			raise
		finally:
			if not self.list_view:
				self.log()
				self.log(["Success:",str(self.successful)])
				self.log(["Warning:",str(self.warned)])
				self.log(["Skipped:",str(self.skipped)])
				self.log(["Errored:",str(self.errored)])

	def chain(self,url,ref = ""):
		import http.client
		import urllib.parse

		URL = urllib.parse.urlparse(url)

		if not isinstance(URL,urllib.parse.ParseResult):
			return

		URL = URL._replace(params='')
		URL = URL._replace(fragment='')
		if not self.extended:
			URL = URL._replace(query='')

		url = urllib.parse.urlunparse(URL)

		if not re.search('^(.*\.)?' + self.domain, URL.netloc):
			if url not in self.visited_external:
				if re.search('\.(' + '|'.join(self.static_extensions) + ')', URL.path):
					self.visited_external.append(url)
					msg = [url]
					if not self.list_view:
						msg.insert(0,"SKIP")
						if not self.noreferrer:
							msg.append("(Ref: " + ref + ")")
					self.log(msg,self.external_static and self.verbose)
			return

		if url not in self.visited:
			self.visited.append(url)
			if re.search('\.(' + '|'.join(self.static_extensions) + ')', URL.path):
				msg = [url]
				if not self.list_view:
					msg.insert(0,"SKIP")
					if not self.noreferrer:
						msg.append("(Ref: " + ref + ")")
				self.log(msg,self.verbose)
				self.skipped += 1
				return

			html = urlopen(Request(url, headers={'User-Agent': 'HadornBot/1.0'}))
			html_page = html.read()
			html_code = html.getcode()

			msg = [url]
			if html_code == 200:
				if not self.list_view:
					msg.insert(0,"OK")
					if not self.noreferrer:
						msg.append("(Ref: " + ref + ")")
				self.log(msg,not self.only_static and not self.quiet)
				self.successful += 1
			else:
				msg.insert(0,"Status" + str(html_code))
				if not self.noreferrer:
					msg.append("(Ref: " + ref + ")")
				self.log(msg,not self.only_static and not self.quiet and not self.list_view)
				self.warned += 1

			soup = BeautifulSoup(html_page,'html.parser')
			for link in soup.findAll("a"):
				if self.recursive > 0:
					if self.recursive > self.recursive_counter:
						self.recursive_counter += 1
						self.chain(link.get('href'),url)
						self.recursive_counter -= 1
				elif self.recursive == 0:
					self.chain(link.get('href'),url)


if __name__ == "__main__":
	main = UT(sys.argv[1:])
