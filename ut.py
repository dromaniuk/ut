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
	recursive = 0

	def read_params(self,mainargs):
		try:
			opts, args = getopt.getopt(mainargs, "hvqer:", ["--help","--verbose","--quiet","--secured","--diff"])
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

	def log(self,msg="",display_it = True):
		if display_it:
			print(msg)
		self.logfile.write(msg + "\n")

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
		self.log("Domain: " + self.domain)
		self.log()

		try:
			self.chain(self.starturl)
		except KeyboardInterrupt:
			self.log()
			self.log("Operation Aborted")
		except:
			raise
		finally:
			self.log()
			self.log("Success:\t" + str(self.successful))
			self.log("Warning:\t" + str(self.warned))
			self.log("Skipped:\t" + str(self.skipped))
			self.log("Errored:\t" + str(self.errored))

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
				if re.search('\.(jpg|png|pdf|jpeg|mp3|mp4|gif|eps|exe|dmg|zip|tar|gz|deb|rpm)', URL.path):
					self.visited_external.append(url)
					self.log("SKIP" + "\t" + url + "\t(Ref: " + ref + ")", self.verbose)
			return

		if url not in self.visited:
			self.visited.append(url)
			if re.search('\.(jpg|png|pdf|jpeg|mp3|mp4|gif|eps|exe|dmg|zip|tar|gz|deb|rpm)', URL.path):
				self.log("SKIP" + "\t" + url + "\t(Ref: " + ref + ")", self.verbose)
				self.skipped += 1
				return

			html = urlopen(Request(url, headers={'User-Agent': 'HadornBot/1.0'}))
			html_page = html.read()
			html_code = html.getcode()

			if html_code == 200:
				self.log("OK" + "\t" + url + "\t(Ref: " + ref + ")", not self.quiet)
				self.successful += 1
			else:
				self.log("Status " + str(html_code) + "\t" + url)
				self.warned += 1

			soup = BeautifulSoup(html_page,'html.parser')
			for link in soup.findAll("a"):
				# print("Recursive: " + str(self.recursive) + "\tCounter:" + str(self.recursive_counter) + "\t Checking...")
				if self.recursive > 0:
					if self.recursive > self.recursive_counter:
						self.recursive_counter += 1
						# print("Incrementing...\tCounter:" + str(self.recursive_counter))
						self.chain(link.get('href'),url)
						self.recursive_counter -= 1
						# print("Decrementing...\tCounter:" + str(self.recursive_counter))
				elif self.recursive == 0:
					self.chain(link.get('href'),url)


if __name__ == "__main__":
	main = UT(sys.argv[1:])
