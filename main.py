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


def get_home_away_for_team(match, team):
	if match['home'] == team:
		return 'home'
	elif match['away'] == team:
		return 'away'
	else:
		None


def reverse_home_away(homeAway):
	if homeAway == 'home':
		return 'away'
	elif homeAway == 'away':
		return 'home'
	else:
		return None


signal.signal(signal.SIGINT, signal_handler)

# GLA, SFS, BOS, SEO, FLA, LDN, NYE, SHD, PHI, HOU, DAL, VAL
once = False
debug = False
user = None
teamSwitches = {
	'SFS': True,
	'GLA': True,
	'BOS': True,
	'PHI': True
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
		elif arg.startswith('only'):
			for team in teamSwitches:
				teamSwitches[team] = False
			teamSwitches[arg[4:]] = True
			log.debug("Only "+arg[4:])
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
					'homeScore': match['scores'][0]['value'],
					'awayScore': match['scores'][1]['value'],
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

			if game['date'] - timedelta(days=7) < datetime.utcnow().replace(tzinfo=timezone.utc) and stageName != "Preseason" and currentStage != stageName:
				log.debug("Setting current stage to: "+stageName)
				currentStage = stageName

			# log.debug("Match: " + game['home'] + " vs " + game['away'] + " at " + game['date'].astimezone(
			# 	timezones['EST']).strftime("%m/%d %I:%M"))

	# for team in teamMatches:
	# 	log.debug(team + ": " + str(len(teamMatches[team])))

	currentTeam = "SFS"
	if teamSwitches[currentTeam]:
		bldr = []
		bldr.append("## UPCOMING MATCH: \n\n")
		bldr.append("Date | vs.\n")
		bldr.append(":---------|:----------:\n")
		nextMatch = 0
		currentTime = datetime.utcnow().replace(tzinfo=timezone.utc)
		for i,match in enumerate(teamMatches[currentTeam]):
			if match['date'] > currentTime:
				nextMatch = i
				break

		match = teamMatches[currentTeam][nextMatch]
		matchDate = match['date'].astimezone(timezones['PST'])
		bldr.append(matchDate.strftime("%b"))
		bldr.append(" ")
		bldr.append(day_with_suffix(matchDate))
		bldr.append("|")
		if match['home'] == currentTeam:
			bldr.append(teams[match['away']])
		else:
			bldr.append(teams[match['home']])
		bldr.append("\n")
		bldr.append("[See full schedule here](https://www.reddit.com/r/SFShock_OW/wiki/matches)\n\n")

		bldr.append("## OVERWATCH LEAGUE | ")
		bldr.append(currentStage)
		bldr.append("\n\n")
		bldr.append("Date | vs. | Final Result\n")
		bldr.append(":---------|:----------:|:----------:\n")
		foundOpponents = [currentTeam]
		for match in stageMatches[currentStage]:
			homeAway = get_home_away_for_team(match, currentTeam)
			if homeAway is not None:
				matchDate = match['date'].astimezone(timezones['PST'])
				bldr.append(matchDate.strftime("%b"))
				bldr.append(" ")
				bldr.append(day_with_suffix(matchDate))
				bldr.append("|")
				bldr.append(teams[match[reverse_home_away(homeAway)]])
				foundOpponents.append(match[reverse_home_away(homeAway)])
				bldr.append("|")

				teamScore = match[homeAway+'Score']
				opponentScore = match[reverse_home_away(homeAway)+'Score']
				if teamScore == 0 and opponentScore == 0:
					bldr.append("N/A")
				else:
					bldr.append(str(teamScore))
					bldr.append(" - ")
					bldr.append(str(opponentScore))
				bldr.append("\n")

		missingOpponents = []
		for team in teams:
			if team not in foundOpponents:
				missingOpponents.append(team)

		for team in missingOpponents:
			bldr.append("X|")
			bldr.append(teams[team])
			bldr.append("|X")


		bldr.append("\n\n\n")

		subreddit = "SFShock_OW"
		wikiPage = r.subreddit(subreddit).wiki['config/sidebar']

		start = wikiPage.content_md[0:wikiPage.content_md.find("## UPCOMING MATCH")]
		end = wikiPage.content_md[wikiPage.content_md.find("## ROSTER:"):]

		if debug:
			log.debug("Subreddit: "+subreddit)
			log.debug("-" * 50)
			log.debug(start +''.join(bldr) + end)
			log.debug("-" * 50)
		else:
			wikiPage.edit(start +''.join(bldr) + end)

	currentTeam = "GLA"
	if teamSwitches[currentTeam]:
		bldr = []
		bldr.append("#**Schedule**\n\n")

		currentStages = ['Preseason', currentStage]
		for stage in currentStages:
			bldr.append("**")
			bldr.append(stage)
			bldr.append("**\n\n")
			bldr.append("Date|Time|Opponent|Result\n")
			bldr.append("---|---|---|---\n")

			for match in stageMatches[stage]:
				homeAway = get_home_away_for_team(match, currentTeam)
				if homeAway is not None:
					matchDate = match['date'].astimezone(timezones['PST'])
					bldr.append(matchDate.strftime("%m/%d|%I:%M"))
					bldr.append("|")
					bldr.append(teams[match[reverse_home_away(homeAway)]])
					bldr.append("|")
					teamScore = match[homeAway+'Score']
					opponentScore = match[reverse_home_away(homeAway)+'Score']
					if teamScore == 0 and opponentScore == 0:
						bldr.append("N/A")
					else:
						hideScores = (matchDate + timedelta(days=7) > datetime.utcnow().replace(tzinfo=timezone.utc))
						if hideScores:
							bldr.append("[")
						bldr.append(str(teamScore))
						bldr.append("-")
						bldr.append(str(opponentScore))
						if hideScores:
							bldr.append("](/spoiler)")

					bldr.append("\n")
			bldr.append("\n")

		bldr.append("\n")

		subreddit = "lagladiators"
		wikiPage = r.subreddit(subreddit).wiki['config/sidebar']

		start = wikiPage.content_md[0:wikiPage.content_md.find("#**Schedule**")]

		if debug:
			log.debug("Subreddit: "+subreddit)
			log.debug("-" * 50)
			log.debug(start +''.join(bldr))
			log.debug("-" * 50)
		else:
			wikiPage.edit(start +''.join(bldr))

	currentTeam = "BOS"
	if teamSwitches[currentTeam]:
		bldr = []
		bldr.append("#Next Match\n\n")
		bldr.append("Watch live on the [Overwatch League](https://overwatchleague.com/en-us/) website!\n")

		nextMatch = teamMatches[currentTeam][0]
		currentTime = datetime.utcnow().replace(tzinfo=timezone.utc)
		for i,match in enumerate(teamMatches[currentTeam]):
			if match['date'] > currentTime:
				nextMatch = match
				break

		bldr.append("######")
		bldr.append(nextMatch['stage'])
		bldr.append("\n\n")
		bldr.append("Date | Against\n")
		bldr.append(":--:|:--:|\n")

		matchDate = nextMatch['date'].astimezone(timezones['EST'])
		bldr.append(matchDate.strftime("%b"))
		bldr.append(". ")
		bldr.append(str(matchDate.day))
		bldr.append(" @ ")
		bldr.append(str(int(matchDate.strftime("%I"))))
		if matchDate.strftime("%M") != '00':
			bldr.append(matchDate.strftime("%M"))
		bldr.append(" ")
		bldr.append(matchDate.strftime("%p").lower())
		bldr.append(" EST")
		bldr.append("|")
		if nextMatch['home'] == currentTeam:
			bldr.append(teams[nextMatch['away']])
		else:
			bldr.append(teams[nextMatch['home']])
		bldr.append("\n\n")

		subreddit = "BostonUprising"
		wikiPage = r.subreddit(subreddit).wiki['config/sidebar']

		start = wikiPage.content_md[0:wikiPage.content_md.find("#Next Match")]
		end = wikiPage.content_md[wikiPage.content_md.find("#Team Roster"):]

		if debug:
			log.debug("Subreddit: "+subreddit)
			log.debug("-" * 50)
			log.debug(start +''.join(bldr) + end)
			log.debug("-" * 50)
		else:
			wikiPage.edit(start +''.join(bldr) + end)

	currentTeam = "PHI"
	if teamSwitches[currentTeam]:
		bldr = []
		bldr.append("**Schedule**\n\n")

		bldr.append(currentStage)
		bldr.append("\n\n")
		bldr.append("Date|Time|Opponent|Result\n")
		bldr.append("---|---|---|---\n")

		for match in stageMatches[currentStage]:
			homeAway = get_home_away_for_team(match, currentTeam)
			if homeAway is not None:
				matchDate = match['date'].astimezone(timezones['EST'])
				bldr.append(matchDate.strftime("%b "))
				bldr.append(str(matchDate.day))
				bldr.append("|")
				bldr.append(str(matchDate.hour))
				bldr.append(matchDate.strftime(" %p"))
				bldr.append("|")
				bldr.append(teams[match[reverse_home_away(homeAway)]])
				bldr.append("|")

				teamScore = match[homeAway+'Score']
				opponentScore = match[reverse_home_away(homeAway)+'Score']
				if teamScore == 0 and opponentScore == 0:
					bldr.append("TBD")
				else:
					bldr.append(str(teamScore))
					bldr.append(" - ")
					bldr.append(str(opponentScore))

				bldr.append("\n")

		bldr.append("\n")

		subreddit = "PHL_Fusion"
		wikiPage = r.subreddit(subreddit).wiki['config/sidebar']

		start = wikiPage.content_md[0:wikiPage.content_md.find("**Schedule**")]
		end = wikiPage.content_md[wikiPage.content_md.find("**Overwatch Related Subreddits**"):]

		if debug:
			log.debug("Subreddit: "+subreddit)
			log.debug("-" * 50)
			log.debug(start +''.join(bldr) + end)
			log.debug("-" * 50)
		else:
			wikiPage.edit(start +''.join(bldr) + end)

	log.debug("Run complete after: %d", int(time.perf_counter() - startTime))
	if once:
		break

	time.sleep(15 * 60)
