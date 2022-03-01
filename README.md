# OSL Repo Extractor

A tool which mines GitHub repositories for [Fabio Marcos'](https://github.com/fabiojavamarcos) NAU-OSL project pipeline.


## Requirements
- Written in `Python 3.8.3`
- Packages:
    - [PyGithub](https://pygithub.readthedocs.io/en/latest/introduction.html)
        - `pip install pygithub`
    - [Cerberus](https://docs.python-cerberus.org/en/stable/)
        - `pip install cerberus`


## Contributing
Using default settings for each, please:
- format all contributions with [black](https://pypi.org/project/black/)
    - `pip install black`
- lint all contributions with [pylint](https://pypi.org/project/pylint/)
    - `pip install pylint`


## Usage
### arguments

```shell
$ python main.py
usage: main.py [-h] extractor_cfg_file
main.py: error: the following arguments are required: extractor_cfg_file
```

The extractor requires only a path to a configuration file. The sample configuration at
`repo-extractor/data/input/configs/sample.json` is a good place to start experimenting. The extractor will report to you
what keys are missing, if any, and whether the values for those keys are acceptable. An acceptable call from the command line
will look like:

```shell
$ python main.py <path/to/cfg/file>
```

### configuration

```shell
~/files/work/repo-extractor/data/input/configs
» cat sample.json
{
    "repo": "JabRef/jabref",
    "state": "closed"
    "auth_file": "/home/m/files/work/repo-extractor/data/input/auths/mp_auth.txt",
    "output_dir": "/home/m/files/work/GitHub-Repo-Extractor-2/data/output",
    "range": [
        270,
        280
    ],
    "commit_fields": [
        "commit_author_name",
        "commit_date",
        "commit_message"
    ],
    "issue_fields": [
        "issue_username"
    ],
    "pr_fields": [
        "pr_body",
        "pr_title"
    ]
}
```

Some key points about the configuration:

- The `auth_file` value requires a path to a file containing a GitHub Personal Access Token. Please format the PAT with no
  extra newlines or trailing spaces. The PAT should be on the first line.

- The `output_dir` will be used to create the necessary outputs for you using the provided repo. You do not need to provide
  a name to an output file nor do you need to create the output directory by hand; it will be created for you if it does not
  exist.  After an execution, the output directory structure will look like `<output_dir>/<repo>/<repo>_output.json`
  e.g. `<output_dir>/jabref/jabref_output.json`

- The `range` value discusses the actual item numbers you want to gather data from. If you want data from PR #270 up to
  PR #280 in a given repository, give [270, 280] to the range key, as above. The range behaves [x, y]; it is inclusive of both values.

- The `fields` keys discuss what pieces of data you want to gather from the objects in the given range. The extractor will
  merge gathered data. For example, if you collected the `pr_body` for objects 1-10 but wanted to gather the `issue_username`
  for those same objects, you can simply change the values of the `fields` keys and run again. The extractor will simply add
  the new data in for each key in the JSON output.
    - You do not need to ask for issue numbers, PR numbers, the PR's merged status. Those pieces of data are mandatory, will
      always be collected, and the commands to access them are private.

### output

During a round of API calls, the extractor will compile gathered outputs into a dictionary. Under two conditions, the
extractor will write output to the output file provided in the configuration:

1. before sleeping when rate-limited by the GitHub REST API
2. after finishing gathering all the data for a range

This means that data will be collected even when the program does not completely finish.

The output produced by the extractor is pretty-printed JSON. Because it is printed in a human-readable format, it is very
easy to see what the extractor has collected and where the program left off in the case that you must stop it. See the
example output at `data/output/jabref/jabref_output.JSON`.

The human-readable output paired with the range functionality discussed above conveniently allows the user to start and stop
at will. For example, you may be collecting data from a very large range but must stop for some reason. You can look at the
output, see what PR or issue number the extractor last collected data for, and use that as the starting value in your range
during your next execution.

### troubleshooting

1. `v2` package does not exists

You likely need to update your `PYTHONPATH` environment variable so that your Python executable knows where to look for packages and modules. To do this, you can modify and paste the `export` statment below into your shell rc file e.g. `~/.bashrc` or `~/.zshrc`:

```shell
export PYTHONPATH='$PYTHONPATH:<path>/GitHub-Repo-Extractor/extractor'
```

In the future, the `v2` source may be collapsed into a monolithic module, eliminating the need for this.


## TODO:
- update README
    - add `state` configuration value into the `configuration` section
    - update `configuration` completely
