# Dependency graph generator
A tool to generate dependency graphs for Gradle-based projects hosted on an organization's GitLab.

It uses GitLab API to fetch project data from repositories and Graphviz to draw thr graphs.

## Install

Run `$ pip install -r requirements.txt`

Download and install Graphviz: https://graphviz.org/download/


## Usage

Run `$ python dep-graph-generator.py`

Or use `-h` for help `$ python dep-graph-generator.py -h`
