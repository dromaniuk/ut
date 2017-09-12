#!/usr/bin/python3.5

from bs4 import BeautifulSoup
from pathlib import Path
from urllib.request import urlopen, Request
import re
import sys
import os
import getopt
import time
import pprint

def main(mainargs):
	global verbose, quiet, domain, starturl, log, extended, secured, successful, skipped, errored, warned

	verbose = False
	quiet = False
	extended = False
	domain = ""
	starturl = None
	secured = False

	try:
		opts, args = getopt.getopt(mainargs, "hvqd:u:es", ["--help","--verbose","--quiet","--domain","--start-url","--extended","--secured"])
	except getopt.GetoptError as err:
		print(err)
		sys.exit(2)

	for o, a in opts:
		if o in ("-v", "--verbose"):
			verbose = True
		elif o in ("-q", "--quiet"):
			quiet = True
		elif o in ("-e", "--extended"):
			extended = True
		elif o in ("-s", "--secured"):
			secured = True
		elif o in ("-h", "--help"):
			print("Help text coming soon")
			sys.exit()
		elif o in ("-u", "--start-url"):
			starturl = a
		else:
			assert False, "unhandled option"
	try:
		for d in args:
			parse(d,starturl)
	except KeyboardInterrupt:
		logstr()
		logstr("Operation Aborted")
		logstr("Success:\t" + str(successful))
		logstr("Warning:\t" + str(warned))
		logstr("Skipped:\t" + str(skipped))
		logstr("Errored:\t" + str(errored))
		logstr()
		pass
	except SystemExit:
		pass
	except e:
		print(e)

def parse(domain,starturl):
	global verbose, quiet, log, homeurl, visited, secured, successful, skipped, errored, warned

	home = str(Path.home())
	workdir = home + "/.ut/"
	try:
		os.stat(workdir)
	except:
		os.mkdir(workdir)	   

	domaindir = workdir + domain + "/"
	try:
		os.stat(domaindir)
	except:
		os.mkdir(domaindir)	   

	datedir = domaindir + time.strftime("%Y-%m-%d") + "/"
	try:
		os.stat(datedir)
	except:
		os.mkdir(datedir)	   

	if secured:
		homeurl = "https://" + domain + "/"
	else:
		homeurl = "http://" + domain + "/"

	if starturl is None:
		starturl = homeurl

	visited = []
	successful = 0
	skipped = 0
	errored = 0
	warned = 0

	log = open(datedir + time.strftime("%H-%M-%S") + ".log","w")
	logstr("Domain: " + domain)
	logstr()
	chain(domain,starturl)
	logstr()
	logstr("Success:\t" + str(successful))
	logstr("Warning:\t" + str(warned))
	logstr("Skipped:\t" + str(skipped))
	logstr("Errored:\t" + str(errored))
	log.close()

def chain(domain,url,ref = ""):
	global verbose, quiet, homeurl, visited, extended, successful, skipped, errored, warned

	urlu = url

	if not url:
		return

	m = re.match('^/([^/].*)', url)
	if m:
		url = homeurl + m.group(1)

	m = re.match("^(http|https)://([^/]+)/([^#]*)", url)
	if m and extended:
		url = m.group(1) + "://" + m.group(2) + "/" + m.group(3)
 
	m = re.match("^(http|https)://([^/]+)/([^\?#]*)", url)
	if m and not extended:
		url = m.group(1) + "://" + m.group(2) + "/" + m.group(3)

	if url not in visited:
		visited.append(url)
		if re.search('^(http|https)://([^/]+\.)?' + domain + "/", url):

			if re.search('\.(jpg|png|pdf|jpeg|mp3)', url):
				visited.append(url)
				logstr("SKIP" + "\t"*4 + url, verbose)
				skipped += 1
				return

			try:
				html_page = urlopen(Request(url, headers={'User-Agent': 'HadornBot/1.0'}))

				if html_page.getcode() == 200:
					logstr("OK" + "\t"*4 + url, not quiet)
					successful += 1
				else:
					logstr("Status " + str(html_page.getcode()) + "\t"*4 + url)
					warned += 1

				soup = BeautifulSoup(html_page,'html.parser')
				for link in soup.findAll("a"):
					chain(domain,link.get('href'),url)

			except Exception as e:
				# pprint.pprint(e)
				logstr(str(e) + "\t"*1 + url + "\t (Ref: " + ref + ")")
				errored += 1

def logstr(msg="",display_it = True):
	global log
	if display_it:
		print(msg)
	log.write(msg + "\n")

if __name__ == "__main__":
	main(sys.argv[1:])
