from os import remove

from bs4 import BeautifulSoup
import requests
import sqlite3
import json
import re
from playwright.sync_api import sync_playwright
#results = open("result.txt","w", encoding="ascii", errors="ignore")
dataBase = sqlite3.connect('DataBase.db')
cursor = dataBase.cursor()
cursor.execute('''
    CREATE TABLE IF NOT EXISTS pulls (
        pullNumber INTEGER PRIMARY KEY,
        comments TEXT,
        added INTEGER,
        removed INTEGER,
        commits TEXT,
        files TEXT,
        links TEXT
    )
    ''')

def removeDuplicates(arr):
    seen = set()
    result = []
    for item in arr:
        if item not in seen:
            seen.add(item)
            result.append(item)
    return result

with sync_playwright() as p:
    browser = p.chromium.launch(headless=True)
    page = browser.new_page()
    for i in range(96 ,155):
        url = f"https://github.com/openssl/openssl/pulls?page={i}&q=is%3Apr+is%3Aclosed"
        #1-615 Pages
        currentPage = requests.get(url)
        soup = BeautifulSoup(currentPage.text, "html.parser")
        target = soup.select_one(
            "body > div.logged-out.env-production.page-responsive "
            "div.application-main div main turbo-frame div div "
            "div.Box.mt-3.Box--responsive.hx_Box--firstRowRounded0 div[role='group'] div.js-navigation-container.js-active-navigation-container"
        )

        if target:
            issueList = target.find_all("div", class_="Box-row Box-row--focus-gray p-0 mt-0 js-navigation-item js-issue-row")



            for issue in issueList:

                data = {}
                tag = issue.get("id")
                pullNumber = tag[tag.find("issue_") + len("issue_"):]
                print(f"\nPull Request #{pullNumber}")
                data["number"] = pullNumber
                #results.write(f"Pull Request #{pullNumber}\n")
                #Converstation page
                pullConvoUrl = f"https://github.com/openssl/openssl/pull/{pullNumber}"
                page.goto(pullConvoUrl)
                page.wait_for_selector("turbo-frame")
                page.wait_for_selector("span.diffstat")
                html = page.content()
                pullConvoSoup = BeautifulSoup(html, "html.parser")

                convoTarget = pullConvoSoup.select_one(
                    "body > div.logged-out.env-production.page-responsive "
                    "div.application-main div main turbo-frame div "
                    "div.clearfix.js-issues-results "
                    "div#discussion_bucket div "
                    "div.Layout-main div"
                )
                if convoTarget:
                    convoTarget = convoTarget.find("div", class_="js-discussion")
                    if convoTarget:
                        messages = []
                        comments = convoTarget.find_all("div", class_=["timeline-comment-group", "unminimized-comment"])
                        for comment in comments:
                            message = ""
                            try:
                                paragraphs = comment.find("div", class_="edit-comment-hide").find("task-lists").find("div").find_all("p")
                                for paragraph in paragraphs:
                                    message += paragraph.text + " "

                                message = message.strip()
                                if message:  #Only append non-empty messages
                                    messages.append(message)

                            except AttributeError:
                                continue
                        if messages:
                            messages.pop(0)  # remove original post

                        messages = removeDuplicates(messages)
                        messageData = ""
                        for item in messages:
                            print(item)
                            messageData = messageData+(item + "\n")
                            #results.write(item + "\n")
                        data["messages"] = messageData
                        goodLinks = []
                        linkData = ""
                        links = convoTarget.find_all("a")
                        for link in links:
                            if link.get("href"):

                                if link.get("href").find("/openssl/openssl/pull/")!= -1:

                                    foundLink = link.get("href")[link.get("href").find("/openssl/openssl/pull/")+22:]
                                    foundLink = foundLink.strip()
                                    if foundLink.find(pullNumber)==-1:

                                        goodLinks.append(foundLink)

                        goodLinks = removeDuplicates(goodLinks)
                        for link in goodLinks:
                            print("Link:", link)

                            linkData = linkData + link+'\n'

                        data['links']=linkData


                    else:
                        data["messages"] = ""
                        print("Convo section not found")
                else:
                    data["messages"] = ""
                    print("Conversation page target not found")


                #Pull request size (part of convo page)
                sizeChangeTarget = pullConvoSoup.find("span",class_="diffstat")


                if sizeChangeTarget:

                    Added = sizeChangeTarget.find("span",class_="color-fg-success").text.strip()
                    Removed = sizeChangeTarget.find("span", class_="color-fg-danger").text.strip()
                    print("Added:"+ Added)
                    data["added"] = Added
                    #results.write("Added:"+ Added + "\n")
                    print("Removed:"+ Removed)
                    data["removed"] = Removed
                    #results.write("Removed:" + Removed+"\n")
                else:



                    data["added"] = "0"
                    data["removed"] = "0"
                    print("Size change target not found")


                #Commits page
                pullCommitsUrl = f"https://github.com/openssl/openssl/pull/{pullNumber}/commits"
                page.goto(pullCommitsUrl)
                page.wait_for_selector("turbo-frame")
                html = page.content()
                pullCommitsSoup = BeautifulSoup(html, "html.parser")

                commitsTarget = pullCommitsSoup.select_one(
                    "body > div.logged-out.env-production.page-responsive "
                    "div.application-main div main turbo-frame div react-app div div div div div div div div div div div "
                    "div.mt-0.prc-Timeline-TimelineBody-WWZY0 div div ul"
                )
                commits = ""
                if commitsTarget:

                    commitsList = commitsTarget.find_all("li", class_="ListItem-module__listItem--kHali CommitRow-module__ListItem_0--PkFAi")
                    for commit in commitsList:
                        commitId = commit.get("data-commit-link")
                        titleModule = commit.find("div", class_="Title-module__container--l9xi7 CommitRow-module__ListItemTitle_0--g9uVv")
                        title = titleModule.find("h4").find("span").find("a").text
                        print(f"Commit: {title} ({commitId})")
                        commits = commits+f"{title} ({commitId})\n"
                        #results.write(f"Commit: {title} ({commitId})\n")
                else:
                    print("No commits found.")

                data["commits"] = commits
                #Files changed page
                pullFilesUrl = f"https://github.com/openssl/openssl/pull/{pullNumber}/files"
                page.goto(pullFilesUrl)
                page.wait_for_selector("turbo-frame")
                html = page.content()
                pullFilesSoup = BeautifulSoup(html, "html.parser")

                fileType = pullFilesSoup.select_one(
                    "body > div[style='word-wrap: break-word;']"
                )
                if fileType:
                    files = ""
                    fileTarget = None
                    classes = fileType.get("class", [])
                    if len(classes) == 4:
                        fileTarget = fileType.select_one(
                            "div.application-main div main turbo-frame div div "
                            "div.position-relative.js-review-state-classes.js-suggested-changes-files-tab div diff-file-filter diff-layout "
                            "div#diff-layout-component "
                            "div[data-target='diff-layout.mainContainer'] div "
                            "div.js-diff-progressive-container"
                        )
                    elif len(classes) == 3:
                        fileTarget = fileType.select_one(
                            "div.application-main div main turbo-frame div div "
                            "div.position-relative.js-review-state-classes.js-suggested-changes-files-tab div diff-file-filter diff-layout "
                            "div.diff-view.js-diff-container "
                            "div.js-diff-progressive-container"
                        )
                    else:
                        print("Unknown page type")
                    if fileTarget:
                        fileList = fileTarget.find_all("copilot-diff-entry")
                        for file in fileList:
                            if file:
                                print("File changed: ", file.get("data-file-path"))
                                files = files+ (file.get("data-file-path"))+"\n"
                                #results.write("File changed:"+ (file.get("data-file-path"))+"\n")
                    else:
                        print("File target not found")

                else:
                    print("File container not found")
                data["files"] = files



                messagesJson = json.dumps(data["messages"])
                commitsJson = json.dumps(data["commits"])
                filesJson = json.dumps(data["files"])
                linksJson = json.dumps(data["links"])
                cursor.execute('''
                        INSERT OR REPLACE INTO pulls (pullNumber, comments, added, removed, commits, files, links)
                        VALUES (?, ?, ?, ?, ?, ?,?)
                    ''', (data["number"], messagesJson, data["added"], data["removed"], commitsJson, filesJson,linksJson))

                dataBase.commit()


        else:
            print("Target container not found")
    dataBase.close()
    browser.close()
