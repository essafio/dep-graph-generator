import graphviz
import gitlab
import argparse
from datetime import datetime

GITLAB_URL = 'YOUR_GITLAB_URL'
ACCESS_TOKEN = 'YOUR_GITLAB_ACCESS_TOKEN'
DEPENDENCY_GROUP_ID = 'ORGANIZATION_GROUP_ID' # example: com.example.something
GROUP_ID = 8 # Developer group
SPECIAL_PROJECT_NAMES = []
PROJECTS_TO_EXCLUDE = []
ONLY_SPECIFIED_PROJECTS = []

gl = gitlab.Gitlab(url=GITLAB_URL, private_token=ACCESS_TOKEN)


def get_project_modules(project):
	project_name = project.attributes['name']
	file_path = 'settings.gradle'

	try:
		file_content = project.files.raw(file_path=file_path, ref=project.attributes['default_branch'])
		file_content = file_content.decode()
		lines = file_content.split("\n")
		lines = [line.strip().replace('include ', '').replace('\'', '').replace('        ', '').replace(',', '') for line in lines if 'include ' in line or '        ' in line]
		return lines
	except Exception as e:
		print(f'warn: could not get {file_path} for {project_name}: {e}')
		return []


def get_module_dependencies(project, module_name, versions):
	project_name = project.attributes['name']
	file_path = f'{module_name}/build.gradle'

	try:
		file_content = project.files.raw(file_path=file_path, ref=project.attributes['default_branch'])
		file_content = file_content.decode()
		lines = file_content.split("\n")
		deps = []
		dep_prefix = DEPENDENCY_GROUP_ID + ':'
		for line in lines:
			if dep_prefix in line:
				dep = line[line.find(dep_prefix) + len(dep_prefix) : line.find(':$')]
				version_name = line[line.find('${versions.') + 11 : line.find('}')]
				deps.append((dep, versions[version_name])) if len(versions) > 0 else deps.append((dep, ''))
			elif 'project(path: ' in line: #dependencies between same project modules
				module_name = line[line.find('project(') + 16 : line.find(')') - 1]  # "project('path: :api')" -> "api"
				deps.append((project_name + '-' + module_name, ''))
			elif 'project(' in line: #dependencies between same project modules
				module_name = line[line.find('project(') + 10 : line.find(')') - 1]  # "project(':api')" -> "api"
				deps.append((project_name + '-' + module_name, ''))

		return deps
	except Exception as e:
		print(f'warn: could not get {file_path} for {project_name}: {e}')
		return []


def get_dependencies_versions(project):
	project_name = project.attributes['name']
	file_path = 'dependencies.gradle'
	versions = {}

	try:
		file_content = project.files.raw(file_path=file_path, ref=project.attributes['default_branch'])
		file_content = file_content.decode()
		lines = file_content.split("\n")
		for line in lines:
			line = line.strip().replace(',', '').replace(' ', '')
			if ':' in line:
				dep_name = line[ : line.find(':')]
				version = line[line.find(':') + 2 : -1]
				versions[dep_name] = version

		return versions
	except Exception as e:
		print(f'warn: could not get {file_path} for {project_name}: {e}')
		return {}


def is_in_projects(dep, projects):
	for project in projects:
		if dep.startswith(project):
			return True
	return False


def is_in_deps(project, deps):
	for a, b, v in deps:
		if a.startswith(project) or b.startswith(project):
			return True
	return False


def create_graph(all_module_to_module_deps, projects_modules, show_dups=False):
	g = graphviz.Digraph(comment='Projects modules dependencies', format='png', engine='fdp')
	g.attr(splines='true', overlap='false')

	if len(ONLY_SPECIFIED_PROJECTS) > 0:
		print(f'info: Drawing graph for projects:')
		nice_print(ONLY_SPECIFIED_PROJECTS)
		all_module_to_module_deps = [(a, b, v) for a, b, v in all_module_to_module_deps if is_in_projects(a, ONLY_SPECIFIED_PROJECTS) or is_in_projects(b, ONLY_SPECIFIED_PROJECTS)]
		new_dict = {}
		for project, modules in projects_modules.items():
			if is_in_deps(project, all_module_to_module_deps):
				 new_dict[project] = modules
		projects_modules = new_dict

	if not show_dups: # duplicated deps between modules
		all_module_to_module_deps = list(dict.fromkeys(all_module_to_module_deps))

	# Draw projects and modules as clusters
	for project in projects_modules:
		with g.subgraph(name=f'cluster_{project}') as c:
			c.attr(style='filled', color='lightblue', label=project, sep='+30', nodesep='0.6')
			for module in projects_modules[project]:
				c.node(project + '-' + module)

	# Draw dependencies
	for a, b, v in all_module_to_module_deps:
		g.edge(a, b)

	g = g.unflatten(stagger=3)
	now = datetime.now().strftime('%Y-%m-%d_%H-%M-%S')
	g.render(f'Dependency-graphs/Modules_graph_{now}.gv', view=True)


def create_graph2(all_project_to_project_deps, projects_modules, show_dups=False):
	g = graphviz.Digraph(comment='Projects dependencies', format='png', engine='neato', node_attr={'fontsize':'16'}) #engines: neato, fdp, sfdp, twopi, circo
	g.attr(splines='true', overlap='scalexy', sep='+20,20', nodesep='0.6')

	if len(ONLY_SPECIFIED_PROJECTS) > 0:
		print(f'info: Drawing graph for projects:')
		nice_print(ONLY_SPECIFIED_PROJECTS)
		all_project_to_project_deps = [(a, b, v) for a, b, v in all_project_to_project_deps if is_in_projects(a, ONLY_SPECIFIED_PROJECTS) or is_in_projects(b, ONLY_SPECIFIED_PROJECTS)]
		new_dict = {}
		for project, modules in projects_modules.items():
			if is_in_deps(project, all_project_to_project_deps):
				 new_dict[project] = modules
		projects_modules = new_dict

	if not show_dups: # duplicated deps between projects
		all_project_to_project_deps = list(dict.fromkeys(all_project_to_project_deps))

	# Draw projects as nodes
	for project_name in projects_modules:
		if project_name not in PROJECTS_TO_EXCLUDE:
			g.node(project_name)

	# Draw dependencies
	for a, b, v in all_project_to_project_deps:
		g.edge(a, b, label=v, labelangle='5', decorate='true')

	g = g.unflatten(stagger=3)
	now = datetime.now().strftime('%Y-%m-%d_%H-%M-%S')
	g.render(f'Dependency-graphs/Projects_graph_{now}.gv', view=True)


def is_project_name_ok(project_name):
	return project_name.endswith('-service') or project_name.endswith('-client') or project_name in SPECIAL_PROJECT_NAMES


def get_project_name_from_dep_name(dependency_name, projects):
	for project in projects:
		if dependency_name.startswith(project.attributes['name']):
			return project.attributes['name']
	return 'unknown-project'


def nice_print(list_to_print):
	for a,b,c in zip(list_to_print[::3], list_to_print[1::3], list_to_print[2::3]):
		print('{:<30}{:<30}{:<}'.format(a, b, c))
	if len(list_to_print) % 3 == 2:
		print('{:<30}{:<}'.format(list_to_print[-2], list_to_print[-1]))
	elif len(list_to_print) % 3 == 1:
		print('{:<}'.format(list_to_print[-1]))


# Get projects in Developer group
def get_projects(group_id):
	group = gl.groups.get(group_id)
	developer_projects = group.projects.list(get_all=True, include_subgroups=True, archived=False)
	print(f'info: Found {len(developer_projects)} projects in group')

	# Filter out projects to be excluded
	developer_projects = [p for p in developer_projects if is_project_name_ok(p.attributes['name'])]
	print(f'info: Projects after filtering: {len(developer_projects)}')
	return developer_projects


def main():
	parser = argparse.ArgumentParser(description='Generate dependency graph for Gradle projects on GitLab.')
	parser.add_argument('--versions', '-v', dest='versions', action="store_true", default=False, help='Display dependencies versions on the graph')
	parser.add_argument('--modules', '-m', dest='modules', action="store_true", default=False, help='Display projects\' internal modules on the graph')
	parser.add_argument('--show-dup', '-d', dest='show_dup', action="store_true", default=False, help='Display duplicated dependencies between projects on the graph')
	parser.add_argument('--projects', '-p', dest='projects', nargs='+', help='Draw graph only for the specified project(s) and their dependencies')
	parser.add_argument('--exclude', '-x', dest='exclude', nargs='+', help='Exclude specified project(s) from the graph')

	args = parser.parse_args()

	if args.exclude != None:
		PROJECTS_TO_EXCLUDE.extend(args.exclude)
		print('info: The following projects will be excluded:')
		nice_print(PROJECTS_TO_EXCLUDE)

	#exit()

	gl.auth() # make sure auth works before going any further

	developer_projects = get_projects(GROUP_ID)
	all_projects_modules = {}
	all_project_to_project_deps = []
	all_module_to_module_deps = []

	# Projects for which dependencies should be fetched
	projects_to_draw = [p.attributes['name'] for p in developer_projects if p.attributes['name'] not in PROJECTS_TO_EXCLUDE]

	if args.projects != None:
		ONLY_SPECIFIED_PROJECTS.extend(args.projects)
		projects_to_draw = [p_name for p_name in projects_to_draw if p_name in ONLY_SPECIFIED_PROJECTS]


	for group_project in developer_projects:
		project = gl.projects.get(group_project.attributes['id']) # Full object with methods etc.
		project_name = project.attributes['name']

		project_modules = get_project_modules(project)
		all_projects_modules[project_name] = project_modules

		if project_name in projects_to_draw:
			versions = get_dependencies_versions(project) if args.versions else {}
			for module in project_modules:
				deps = get_module_dependencies(project, module, versions)
				for dep, ver in deps:
					if args.modules:
						all_module_to_module_deps.append((project_name + '-' + module, dep, ''))
					else:
						proj = get_project_name_from_dep_name(dep, developer_projects)
						if proj != project_name:
							all_project_to_project_deps.append((project_name, proj, ver))

	if args.modules:
		create_graph(all_module_to_module_deps, all_projects_modules, show_dups=args.show_dup)
	else:
		create_graph2(all_project_to_project_deps, all_projects_modules, show_dups=args.show_dup)



if __name__ == "__main__":
    main()






# TODO:
# move global vars to a config/env file
# add dependency in root build.gradle
# add extension as param for script
# add multiprocessing
# add better logs





