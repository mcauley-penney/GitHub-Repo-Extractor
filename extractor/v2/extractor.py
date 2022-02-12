"""
The extractor module provides and exposes functionality to mine GitHub repositories.
"""

import github
from v2 import conf, file_io, sessions

TIME_FMT = "%D, %I:%M:%S %p"


def _clean_str(str_to_clean) -> str:
    """
    If a string is empty or None, returns NaN. Otherwise, strip the string of any
    carriage returns, newlines, and leading or trailing whitespace.

    :param str_to_clean str: string to clean and return
    """
    if str_to_clean is None or str_to_clean == "":
        return "Nan"

    output_str = str_to_clean.replace("\r", "")
    output_str = output_str.replace("\n", "")

    return output_str.strip()


def _get_body(api_obj) -> str:
    """
    return issue or PR text body

    :param api_obj github.PullRequest/github.Issue: API object to get body text of
    """
    return _clean_str(api_obj.body)


def _get_closed_time(api_obj) -> str:
    """
    if the API object has been closed, i.e. closed PR or issue, return the formatted
    datetime that it was closed at

    :param api_obj github.PullRequest/github.Issue: API object to get datetime of
    closing of
    """
    if api_obj.closed_at is not None:
        return api_obj.closed_at.strftime(TIME_FMT)

    return "NaN"


def _get_issue_comments(issue_obj) -> str:
    """
    if a given issue has comments, collect them all into one string separated by a
    special delimeter, format the str, and return it

    :param api_obj github.Issue: Issue object to comments of
    """
    comments_paged_list = issue_obj.get_comments()

    if comments_paged_list.totalCount != 0:
        sep_str = " =||= "

        # get body from each comment, strip of whitespace, and join w/ special char
        comment_str = sep_str.join(
            comment.body.strip() for comment in comments_paged_list
        )

        # strip comment string of \n, \r, and whitespace again
        return _clean_str(comment_str)

    return "NaN"


def _get_page_last_item(paged_list, page_index):
    return paged_list.get_page(page_index)[-1]


def _get_pr_merged(pr_obj) -> bool:
    return pr_obj.merged


def _get_title(api_obj) -> str:
    return api_obj.title


def _get_username(api_obj) -> str:
    return _clean_str(api_obj.user.name)


def _get_userlogin(api_obj) -> str:
    return _clean_str(api_obj.user.login)


def _get_commit_auth_date(api_obj) -> str:
    return api_obj.commit.author.date.strftime(TIME_FMT)


def _get_commit_auth_name(api_obj) -> str:
    return api_obj.commit.author.name


def _get_commit_committer(api_obj) -> str:
    return api_obj.commit.committer.name


def _get_commit_files(api_obj) -> dict:
    """
    For the list of files modified by a commit on a PR, return a list of qualities

    :param api_obj PaginatedList: paginated list of commits

    NOTE:
        If a list of files is too large, it will be returned as a paginatied
        list. See note about the list length constraints at
        https://docs.github.com/en/rest/reference/commits#get-a-commit. As of right
        now, this situation is not handled here.

    :rtype dict[unknown]: dictionary of fields discussing file attributes of a
    commit
    """
    file_list = api_obj.files

    commit_file_list = []
    commit_adds = 0
    commit_changes = 0
    commit_patch_text = ""
    commit_removes = 0
    commit_status_str = ""

    for file in file_list:
        commit_file_list.append(file.filename)
        commit_adds += int(file.additions)
        commit_changes += int(file.changes)
        commit_patch_text += str(file.patch) + ", "
        commit_removes += int(file.deletions)
        commit_status_str += str(file.status) + ", "

    quoted_commit_status_str = '"' + commit_status_str + '"'

    return {
        "file_list": commit_file_list,
        "additions": commit_adds,
        "changes": commit_changes,
        "patch_text": _clean_str(commit_patch_text),
        "removals": commit_removes,
        "status": _clean_str(quoted_commit_status_str),
    }


def _get_commit_msg(api_obj) -> str:
    return _clean_str(api_obj.commit.message)


def _get_commit_sha(api_obj) -> str:
    return api_obj.sha


def _merge_dicts(base: dict, to_merge: dict) -> dict:
    """
    Merge two dictionaries
    NOTES:
        • syntax in 3.9 or greater is "base |= to_merge"
            • pipe is the "merge operator"

    :param base: dict to merge into
    :type base: dict
    :param to_merge: dict to dissolve into base dict
    :type to_merge: dict
    :return: base dict
    :rtype: dict
    """
    return {**base, **to_merge}


class Extractor:
    """
    The Extractor class contains and executes GitHub REST API functionality. It
    initiates and holds onto an object that stores the configuration for the program
    execution, an object that initiates and contains a connection to the GitHub API, and
    an object that writes content to JSON files.
    """

    # init dispatch tables that allow us to use strings to access functions
    # intro: https://betterprogramming.pub/dispatch-tables-in-python-d37bcc443b0b
    __COMMIT_CMD_DISPATCH = {
        "commit_author_name": _get_commit_auth_name,
        "committer": _get_commit_committer,
        "commit_date": _get_commit_auth_date,
        "commit_files": _get_commit_files,
        "commit_message": _get_commit_msg,
        "commit_sha": _get_commit_sha,
    }

    __ISSUE_CMD_DISPATCH = {
        "issue_body": _get_body,
        "issue_closed": _get_closed_time,
        "issue_comments": _get_issue_comments,
        "issue_title": _get_title,
        "issue_userlogin": _get_userlogin,
        "issue_username": _get_username,
    }

    __PR_CMD_DISPATCH = {
        "pr_body": _get_body,
        "pr_closed": _get_closed_time,
        "__pr_merged": _get_pr_merged,
        "pr_title": _get_title,
        "pr_userlogin": _get_userlogin,
        "pr_username": _get_username,
    }

    # See cerberus documentation for schema rules:
    # https://docs.python-cerberus.org/en/stable/index.html
    #
    # Above you can see a large amount of private getter methods that interact with
    # GitHub API objects and a few dictionaries that point to these methods. They have
    # been placed there because this position allows them to be referenced in this
    # schema. This cerberus schema defines what is and is not acceptable as inputs to
    # the program, specifically to the configuration object. We want to define this
    # AFTER we have defined our dispatch tables (the dictionaries above) because the
    # dictionary keys can then be used to define what fields are acceptable in the
    # "fields" schema fields. As you can see below, we unpack the dictionary keys into
    # a list ('*' is the unpack operator. Unpacking a dictionary retrieves the keys and
    # the square brackets contains the keys in a list) and that list acts as the
    # definition of what is acceptable in that field in the incoming configuration
    # JSON. This means that all you have to do to teach the configuration what is
    # acceptable in those fields is to add or remove the keys in the dicts above. For
    # example, if you decide that you want to allow the user to get a new item from PR
    # objects, such as the date the PR was made, you can just add a key to the dict and
    # the configuration will then know that it is allowed. This makes adding the ability
    # to get new information from the API expedient
    #
    # As an aside, placing the private getter methods above the dict definitions allow
    # them to be used in the dict as vals
    CFG_SCHEMA = {
        "repo": {"type": "string"},
        "auth_file": {"type": "string"},
        "state": {"allowed": ["closed", "open"], "type": "string"},
        "range": {"min": [0, 0], "schema": {"type": "integer"}, "type": "list"},
        "commit_fields": {
            "allowed": [*__COMMIT_CMD_DISPATCH],
            "schema": {"type": "string"},
            "type": "list",
        },
        "issues_fields": {
            "allowed": [*__ISSUE_CMD_DISPATCH],
            "schema": {"type": "string"},
            "type": "list",
        },
        "pr_fields": {
            "allowed": [*__PR_CMD_DISPATCH],
            "schema": {"type": "string"},
            "type": "list",
        },
        "output_dir": {"type": "string"},
    }

    def __init__(self, cfg_path) -> None:
        """
        Initialize an extractor object. This object is our top-level actor and must be
        used by the user to extract data, such as in a driver program
        """
        # read configuration dictionary from input configuration file
        cfg_dict = file_io.read_json_to_dict(cfg_path)

        # initialize configuration object with cfg dict
        self.cfg = conf.Cfg(cfg_dict, self.CFG_SCHEMA)

        auth_path = self.get_cfg_val("auth_file")

        # initialize authenticated GitHub session
        self.gh_sesh = sessions.GithubSession(auth_path)

        self.pr_paged_list = self.__get_paged_list("pr")
        self.issues_paged_list = self.__get_paged_list("issues")

    def _get_api_item_indices(self, paged_list, range_list: list) -> list:
        """
        sanitize our range values so that they are guaranteed to be safe, find the
        indices of those values inside of the paginated list, and return

        :param paged_list; Github.PaginatedList of Github.Issues or Github.PullRequests:
            list of API objects

        :param range_list list[int]: list of range beginning and end values that we wish
        to find in the given paginated list

        :rtype int: list of indices to the paginated list of items that we wish to find
        """

        def __bin_search_in_list(paged_list, last_page_index: int, val: int) -> int:
            """
            iterative binary search which finds the page of an item that we are looking
            for, such as a PR or issue, inside of a list of pages of related objects
            from the GitHub API.

            :param paged_list: paginated list of issues or PRs
            :type paged_list:Github.PaginatedList of Github.Issues or
            Github.PullRequests
            :param val: number of item in list that we desire; e.g. PR# 800
            :type val: int
            :return: index of page in paginated list param where val param is located
            :rtype: int
            """
            low = 0
            high = last_page_index

            while low < high - 1:
                mid = (low + high) // 2

                mid_first_val = paged_list.get_page(mid)[0].number
                mid_last_val = _get_page_last_item(paged_list, mid).number

                # if the value we want is greater than the first item (cur_val -
                # page_len) on the middle page but less than the last item, it is in
                # the middle page
                if mid_first_val <= val <= mid_last_val:
                    return mid

                if val < mid_first_val:
                    high = mid - 1

                elif val > mid_last_val:
                    low = mid + 1

            return low

        def __bin_search_in_page(paged_list_page, page_len: int, val: int) -> int:
            """
            iterative binary search modified to return either the exact index of the
            item with the number the user desires or the index of the item beneath that
            value in the case that the value does not exist in the list. An example
            might be that a paginated list of issues does not have #'s 9, 10, or 11, but
            the user wants to begin looking for data at #10. This binary search should
            return the index of the API object with the number 8.

            :param paged_list_page PaginatedList[Github.Issues|Github.PullRequests]:
                list of API objects

            :param val int: the value that we wish to find the index of, e.g. the index
            of PR #10

            :rtype int: index of the object we are looking for
            """
            low = 0

            # because this binary search is looking through lists that may have items
            # missing, we want to be able to return the index of the nearest item before
            # the item we are looking for. Therefore, we stop when low is one less than
            # high. This allows us to take the lower value when a value does not exist
            # in the list.
            while low < page_len - 1:
                mid = (low + page_len) // 2

                cur_val = paged_list_page[mid].number

                if val == cur_val:
                    return mid

                if val < cur_val:
                    page_len = mid - 1

                elif val > cur_val:
                    low = mid + 1

            return low

        page_len = self.gh_sesh.get_pg_len()
        out_list = []

        print(f"{' ' * 4}Sanitizing range configuration values...")

        # get index of last page in paginated list
        last_page_index = (paged_list.totalCount - 1) // page_len

        # get the highest item num in the paginated list of items, e.g. very last PR num
        highest_num = _get_page_last_item(paged_list, last_page_index).number

        # get sanitized range. This will correct any vals given in the range cfg so that
        # they are within the values that are in the paged list. We are protected from
        # too low of values by the Cerberus config schema, so this process only looks at
        # values that are too high.
        clean_range_tuple = (
            min(val, highest_num) for val in (range_list[0], range_list[-1])
        )

        print(
            f"{' ' * 4}finding start and end indices corresponding to range values..."
        )

        # for the two boundaries in the sanitized range
        for val in clean_range_tuple:

            # use binary search to find the index of the page inside of the list of
            # pages that contains the item number, e.g. PR# 600, that we want
            page_index = __bin_search_in_list(paged_list, last_page_index, val)

            # use iterative binary search to find item in correct page of linked list
            item_page_index = __bin_search_in_page(
                paged_list.get_page(page_index), page_len, val
            )

            # the index of the item in the total list is the page index that it is on
            # multiplied by the amount of items per page, summed with the index of the
            # item in the page, e.g. if the item is on index 20 of page 10 and there are
            # 30 items per page, its index in the list is 20 + (10 * 30)
            item_list_index = item_page_index + (page_index * page_len)

            print(
                f"{' ' * 8}item #{val} found at index {item_list_index} in the paginated list..."
            )

            # the index of the items we need is the amount of items per page that were
            # skipped plus the index of the item in it's page
            out_list.append(item_list_index)

        print()

        return out_list

    def get_cfg_val(self, key: str):
        """
        :param key: key of desired value from configuration dict to get
        :type key: str
        :return: value from configuration associated with given key
        :rtype: [str | int]
        """
        return self.cfg.get_cfg_val(key)

    def get_issues_data(self) -> None:
        """
        retrieves issue data from the GitHub API; uses the "range" configuration value
        to determine what indices of the issue paged list to look at and the
        "issues_fields" field to determine what information it should retrieve from
        each issues of interest

        :raises github.RateLimitExceededException: if rate limited by the GitHub REST
        API, dump collected data to output file and sleep the program until calls can be
        made again
        """

        data_dict = {"issue": {}}

        # get output file path
        out_file = self.get_cfg_val("output_file")

        # get indices of sanitized range values
        val_range = self.get_cfg_val("range")
        range_list = self._get_api_item_indices(self.issues_paged_list, val_range)

        # unpack vals
        start_val = range_list[0]
        end_val = range_list[1]

        print("Beginning issue extraction. Starting may take a moment...\n")

        while start_val < end_val + 1:
            try:
                cur_issue = self.issues_paged_list[start_val]
                cur_issue_num = str(cur_issue.number)

                cur_item_data = {
                    field: self.__ISSUE_CMD_DISPATCH[field](cur_issue)
                    for field in self.get_cfg_val("issues_fields")
                }

                cur_entry = {cur_issue_num: cur_item_data}

            except github.RateLimitExceededException:
                file_io.write_merged_dict_to_json(data_dict, out_file)
                data_dict.clear()
                self.gh_sesh.sleep_gh_session()

            else:
                data_dict["issue"] = _merge_dicts(data_dict["issue"], cur_entry)
                self.gh_sesh.print_rem_gh_calls()

                start_val += 1

        file_io.write_merged_dict_to_json(data_dict, out_file)

    def __get_paged_list(self, list_type):
        """
        retrieves and stores a paginated list from GitHub

        :param list_type str: type of paginated list to retrieve

        :raises github.RateLimitExceededException: if rate limited by the GitHub REST
        API, sleep the program until calls can be made again and continue attempt to
        collect desired paginated list

        :rtype None: sets object member to paginated list object
        """
        job_repo = self.get_cfg_val("repo")
        item_state = self.get_cfg_val("state")

        while True:
            try:
                # retrieve GitHub repo object
                repo_obj = self.gh_sesh.session.get_repo(job_repo)

                if list_type == "issues":
                    return repo_obj.get_issues(
                        direction="asc", sort="created", state=item_state
                    )

                return repo_obj.get_pulls(
                    direction="asc", sort="created", state=item_state
                )

            except github.RateLimitExceededException:
                self.gh_sesh.sleep_gh_session()

    def get_pr_data(self) -> None:
        """
        retrieves both PR and commit data from the GitHub API; uses the "range"
        configuration value to determine what indices of the PR paged list to
        look at and the "pr_fields" and "commit_fields" configurationfields to
        determine what information it should retrieve from each PR of interest.

        commits are included by default because the commit info we are interested in
        descends from and is retrievable via PRs, i.e. we are not intereseted in
        commits that
            1. are not from a closed and merged PR
            2. have no files changed by the commit

        :raises github.RateLimitExceededException: if rate limited by the GitHub REST
        API, dump collected data to output file and sleep the program until calls can
        be made again

        :rtype None
        """

        def __get_last_commit(pr_obj):
            """
            gets the paginated list of commits from a given pr, then returns the very
            last commit in that list of commits

            :param pr_obj Github.PullRequest: pr to source commit info from

            :rtype Github.Commit: last commit in the list of commits for current PR
            """
            # get paginated list of commits for PR at current index
            cur_commit_list = pr_obj.get_commits()

            # get index of commit we want from len of paginated list of commits
            last_commit_index = cur_commit_list.totalCount - 1

            # use that index to get the commit we are interested in
            return cur_commit_list[last_commit_index]

        data_dict = {"pr": {}}

        out_file = self.get_cfg_val("output_file")

        # get indices of sanitized range values
        range_list = self._get_api_item_indices(
            self.pr_paged_list, self.get_cfg_val("range")
        )

        # unpack vals
        start_val = range_list[0]
        end_val = range_list[1]

        print(
            "Beginning pull request/commit extraction. Starting may take a moment...\n"
        )

        while start_val < end_val + 1:
            try:
                # get current PR to begin information gathering
                cur_pr = self.pr_paged_list[start_val]

                is_merged = cur_pr.merged

                # create dict to build upon. This variable will later become the val of
                # a dict entry, making it a subdictionary
                cur_entry = {"__pr_merged": is_merged}

                # if the current PR number is greater than or equal to the first
                # number provided in the "range" cfg val and the PR is merged
                if is_merged or self.get_cfg_val("state") == "open":
                    cur_entry_data = {
                        field: self.__PR_CMD_DISPATCH[field](cur_pr)
                        for field in self.get_cfg_val("pr_fields")
                    }

                    cur_entry = _merge_dicts(cur_entry, cur_entry_data)

                    last_commit = __get_last_commit(cur_pr)

                    # if there are files changed for this commit
                    if len(last_commit.files) > 0:

                        # get all data from that commit
                        cur_entry_data = {
                            field: self.__COMMIT_CMD_DISPATCH[field](last_commit)
                            for field in self.get_cfg_val("commit_fields")
                        }

                        cur_entry = _merge_dicts(cur_entry, cur_entry_data)

                # use all gathered entry data as the val for the PR num key
                cur_entry = {str(cur_pr.number): cur_entry}

            except github.RateLimitExceededException:
                file_io.write_merged_dict_to_json(data_dict, out_file)
                data_dict.clear()
                self.gh_sesh.sleep_gh_session()

            else:
                data_dict["pr"] = _merge_dicts(data_dict["pr"], cur_entry)
                self.gh_sesh.print_rem_gh_calls()

                start_val += 1

        file_io.write_merged_dict_to_json(data_dict, out_file)
