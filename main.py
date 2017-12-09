#!/usr/bin/python3

import praw
import os
import logging.handlers
import time
import sys
import configparser
import signal
import requests
import traceback
from datetime import datetime
from datetime import timezone
from datetime import timedelta

### Config ###
LOG_FOLDER_NAME = "logs"
SUBREDDIT = "default"
USER_AGENT = "OWL reddit bot (by /u/Watchful1)"
LOOP_TIME = 15
REDDIT_OWNER = "Watchful1"

timezones = {'EST': timezone(timedelta(hours=-5)),
             'CST': timezone(timedelta(hours=-6)),
             'MST': timezone(timedelta(hours=-7)),
             'PST': timezone(timedelta(hours=-8))
             }

### Logging setup ###
LOG_LEVEL = logging.DEBUG
if not os.path.exists(LOG_FOLDER_NAME):
	os.makedirs(LOG_FOLDER_NAME)
LOG_FILENAME = LOG_FOLDER_NAME + "/" + "bot.log"
LOG_FILE_BACKUPCOUNT = 5
LOG_FILE_MAXSIZE = 1024 * 256

log = logging.getLogger("bot")
log.setLevel(LOG_LEVEL)
log_formatter = logging.Formatter('%(asctime)s - %(levelname)s: %(message)s')
log_stderrHandler = logging.StreamHandler()
log_stderrHandler.setFormatter(log_formatter)
log.addHandler(log_stderrHandler)
if LOG_FILENAME is not None:
	log_fileHandler = logging.handlers.RotatingFileHandler(LOG_FILENAME, maxBytes=LOG_FILE_MAXSIZE,
	                                                       backupCount=LOG_FILE_BACKUPCOUNT)
	log_formatter_file = logging.Formatter('%(asctime)s - %(levelname)s - %(message)s')
	log_fileHandler.setFormatter(log_formatter_file)
	log.addHandler(log_fileHandler)


def signal_handler(signal, frame):
	log.info("Handling interupt")
	quit()


def day_with_suffix(date):
	suffix = 'th' if 11 <= date.day <= 13 else {1: 'st', 2: 'nd', 3: 'rd'}.get(date.day % 10, 'th')
	return str(date.day) + suffix


signal.signal(signal.SIGINT, signal_handler)

once = False
debug = False
user = None
teamSwitches = {
	'SFS': True,
	'GLA': True,
	'BOS': True
}
if len(sys.argv) >= 2:
	user = sys.argv[1]
	for arg in sys.argv:
		if arg == 'once':
			once = True
		elif arg == 'debug':
			debug = True
		elif arg.startswith('no'):
			teamSwitches[arg[2:]] = False
			log.debug("Skipping "+arg[2:])
else:
	log.error("No user specified, aborting")
	sys.exit(0)

log.debug("Connecting to reddit")

try:
	r = praw.Reddit(
		user
		, user_agent=USER_AGENT)
except configparser.NoSectionError:
	log.error("User " + user + " not in praw.ini, aborting")
	sys.exit(0)

log.info("Logged into reddit as /u/" + str(r.user.me()))

while True:
	startTime = time.perf_counter()
	log.debug("Starting run")

	url = "https://api.overwatchleague.com/schedule"
	try:
		requestTime = time.perf_counter()
		json = requests.get(url, headers={'User-Agent': USER_AGENT})
		requestSeconds = int(time.perf_counter() - requestTime)
		if json.status_code != 200:
			log.warning("Could not parse schedule, status: " + str(json.status_code))
		stages = json.json()['data']['stages']
	except Exception as err:
		log.warning("Could not parse schedule")
		log.warning(traceback.format_exc())

	matches = []
	stageMatches = {}
	teamMatches = {}
	teams = {}
	currentStage = "Stage 1"
	for stage in stages:
		stageName = stage['name']
		stageMatches[stageName] = []
		for match in stage['matches']:
			if match['competitors'][0] is None or match['competitors'][1] is None:
				continue
			game = {'home': match['competitors'][0]['abbreviatedName'],
					'away': match['competitors'][1]['abbreviatedName'],
					'date': datetime.strptime(match['startDate'], "%Y-%m-%dT%H:%M:%S.000Z").replace(
						tzinfo=timezone.utc),
					'stage': stageName
					}
			matches.append(game)
			stageMatches[stageName].append(game)
			if game['home'] not in teamMatches:
				teamMatches[game['home']] = []
			if game['away'] not in teamMatches:
				teamMatches[game['away']] = []
			if game['home'] not in teams:
				teams[game['home']] = match['competitors'][0]['name']
			if game['away'] not in teams:
				teams[game['away']] = match['competitors'][1]['name']

			teamMatches[game['home']].append(game)
			teamMatches[game['away']].append(game)

			if game['date'] - timedelta(days=7) < datetime.utcnow() and stageName != "Preseason" and currentStage != stageName:
				log.debug("Setting current stage to: "+stageName)
				currentStage = stageName

			# log.debug("Match: " + game['home'] + " vs " + game['away'] + " at " + game['date'].astimezone(
			# 	timezones['EST']).strftime("%m/%d %I:%M"))

	# for team in teamMatches:
	# 	log.debug(team + ": " + str(len(teamMatches[team])))

	currentTeam = "SFS"
	if teamSwitches[currentTeam]:
		SFSString = []
		SFSString.append("## UPCOMING MATCH: \n\n")
		SFSString.append("Date | vs.\n")
		SFSString.append(":---------|:----------:\n")
		nextMatch = 0
		currentTime = datetime.utcnow().replace(tzinfo=timezone.utc)
		for i,match in enumerate(teamMatches[currentTeam]):
			if match['date'] > currentTime:
				nextMatch = i
				break

		match = teamMatches[currentTeam][nextMatch]
		matchDate = match['date'].astimezone(timezones['PST'])
		SFSString.append(matchDate.strftime("%b"))
		SFSString.append(" ")
		SFSString.append(day_with_suffix(matchDate))
		SFSString.append("|")
		if match['home'] == currentTeam:
			SFSString.append(teams[match['away']])
		else:
			SFSString.append(teams[match['home']])
		SFSString.append("\n")
		SFSString.append("[See full schedule here](https://www.reddit.com/r/SFShock_OW/wiki/matches)\n\n")

		stageName = "Stage 1"
		SFSString.append("## OVERWATCH LEAGUE | ")
		SFSString.append(stageName)
		SFSString.append("\n\n")
		SFSString.append("Date | vs. | Final Result\n")
		SFSString.append(":---------|:----------:|:----------:\n")
		foundOpponents = [currentTeam]
		for match in stageMatches[stageName]:
			if match['home'] == currentTeam or match['away'] == currentTeam:
				matchDate = match['date'].astimezone(timezones['PST'])
				SFSString.append(matchDate.strftime("%b"))
				SFSString.append(" ")
				SFSString.append(day_with_suffix(matchDate))
				SFSString.append("|")
				if match['home'] == currentTeam:
					SFSString.append(teams[match['away']])
					foundOpponents.append(match['away'])
				else:
					SFSString.append(teams[match['home']])
					foundOpponents.append(match['home'])
				SFSString.append("|")
				SFSString.append("N/A")
				SFSString.append("\n")

		missingOpponents = []
		for team in teams:
			if team not in foundOpponents:
				missingOpponents.append(team)

		for team in missingOpponents:
			SFSString.append("X|")
			SFSString.append(teams[team])
			SFSString.append("|X")


		SFSString.append("\n\n\n")

		subreddit = "SFShock_OW"
		wikiPage = r.subreddit(subreddit).wiki['config/sidebar']

		start = wikiPage.content_md[0:wikiPage.content_md.find("## UPCOMING MATCH")]
		end = wikiPage.content_md[wikiPage.content_md.find("## ROSTER:"):]

		if debug:
			log.debug("Subreddit: "+subreddit)
			log.debug("-" * 50)
			log.debug(start+''.join(SFSString)+end)
			log.debug("-" * 50)
		else:
			wikiPage.edit(start+''.join(SFSString)+end)

	currentTeam = "GLA"
	if teamSwitches[currentTeam]:
		GLAString = []
		GLAString.append("#**Schedule**\n\n")

		stages = ["Preseason","Stage 1"]
		for stage in stages:
			GLAString.append("**")
			GLAString.append(stage)
			GLAString.append("**\n\n")
			GLAString.append("Date|Time| |Opponent|Result\n")
			GLAString.append("---|---|---|---|---\n")

			for match in stageMatches[stage]:
				if match['home'] == currentTeam or match['away'] == currentTeam:
					GLAString.append(match['date'].astimezone(timezones['PST']).strftime("%m/%d|%I:%M"))
					GLAString.append("||")
					if match['home'] == currentTeam:
						GLAString.append(teams[match['away']])
					else:
						GLAString.append(teams[match['home']])
					GLAString.append("|")
					GLAString.append("N/A")

					GLAString.append("\n")

			GLAString.append("\n")

		subreddit = "lagladiators"
		wikiPage = r.subreddit(subreddit).wiki['config/sidebar']

		start = wikiPage.content_md[0:wikiPage.content_md.find("#**Schedule**")]

		if debug:
			log.debug("Subreddit: "+subreddit)
			log.debug("-" * 50)
			log.debug(start +''.join(GLAString))
			log.debug("-" * 50)
		else:
			wikiPage.edit(start +''.join(GLAString))

	currentTeam = "BOS"
	if teamSwitches[currentTeam]:
		BOSString = []
		BOSString.append("#Next Match\n\n")
		BOSString.append("Watch live on the [Overwatch League](https://overwatchleague.com/en-us/) website!\n")

		nextMatch = teamMatches[currentTeam][0]
		currentTime = datetime.datetime.utcnow().replace(tzinfo=timezone.utc)
		for i,match in enumerate(teamMatches[currentTeam]):
			if match['date'] > currentTime:
				nextMatch = match
				break

		BOSString.append("######")
		BOSString.append(nextMatch['stage'])
		BOSString.append("\n\n")
		BOSString.append("Date | Against\n")
		BOSString.append(":--:|:--:|\n")

		matchDate = nextMatch['date'].astimezone(timezones['EST'])
		BOSString.append(matchDate.strftime("%b"))
		BOSString.append(". ")
		BOSString.append(str(matchDate.day))
		BOSString.append(" @ ")
		BOSString.append(str(int(matchDate.strftime("%I"))))
		if matchDate.strftime("%M") != '00':
			BOSString.append(matchDate.strftime("%M"))
		BOSString.append(" ")
		BOSString.append(matchDate.strftime("%p").lower())
		BOSString.append(" EST")
		BOSString.append("|")
		if nextMatch['home'] == currentTeam:
			BOSString.append(teams[nextMatch['away']])
		else:
			BOSString.append(teams[nextMatch['home']])
		BOSString.append("\n\n")

		subreddit = "BostonUprising"
		wikiPage = r.subreddit(subreddit).wiki['config/sidebar']

		start = wikiPage.content_md[0:wikiPage.content_md.find("#Next Match")]
		end = wikiPage.content_md[wikiPage.content_md.find("#Team Roster"):]

		if debug:
			log.debug("Subreddit: "+subreddit)
			log.debug("-" * 50)
			log.debug(start+''.join(BOSString)+end)
			log.debug("-" * 50)
		else:
			wikiPage.edit(start+''.join(BOSString)+end)


	log.debug("Run complete after: %d", int(time.perf_counter() - startTime))
	if once:
		break

	time.sleep(15 * 60)
