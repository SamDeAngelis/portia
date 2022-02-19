from neo4j import GraphDatabase
from neo4j import exceptions
import get_dc_data
import os
#import click

#Run these before run_cli_scan can run
driver = GraphDatabase.driver(os.environ.get('NEO4J_DB'),
                                  auth=(os.environ.get('NEO4J_USER'), os.environ.get('NEO4J_PWD')))
tx = driver.session()

def neo4JCheck():
    print("Validating neo4j instance",flush=True)
    try:
        tx.run(''' MATCH (n) RETURN n ''')  #Runs a Generic Query to try and connect to the database
        print("A valid NEO4J existance!",flush=True)
    except exceptions.ServiceUnavailable:
        print("Error: Invalid neo4j instace\nPlease make sure neo4j is installed and running")
        exit(1)
    except exceptions.AuthError:
        print("Error: Invalid neo4j credentials\nPlease make sure your credentials are correct")
        exit(1)

#@click.command()
#@click.argument('project', required=True)
#@click.argument('file', required=False)
def run_cli_scan(project, file):
    if not file:
        file = 'dependency-check-report.json'
    project = project
    deps, vulns = get_dc_data.get_depcheck_data(project, file)
    if deps:
        ingest_project(project)
        ingest_dependencies(deps, project)
        ingest_vulns(vulns)
        create_vuln_relations()
        create_project_relations()
        add_label_colors()
        print("Data successfully ingested in Neo4J")
    else:
        print("No data has been ingested")
    driver.close() #Added to close the Driver

def ingest_project(project):
    tx.run('''
    MERGE (n:project {project_name: $project})
    ''', project=project)


def ingest_vulns(vulns_list):
    tx.run('''    UNWIND $mapEntry AS mItem
              CALL apoc.merge.node(["vulnerability"],
              {vulnerability_name:mItem["CVE"],
              severity:mItem["CVSSv3"],
              severity_desc:mItem["severity_desc"]})
              YIELD node
              return node
            '''
           , mapEntry=vulns_list)


def ingest_dependencies(dependencies, project):
    for dependency in dependencies:
        r = tx.run('''
          MATCH (d:dependency {dependency: $dependency})
          return d
                 ''', dependency=dependency.get('dependency'))
        if r.single():
            tx.run('''
          MATCH (d:dependency {dependency: $dependency})
          WHERE NOT ($projects  IN d.projects)
          SET d.projects = d.projects + $projects
                 ''',
                   dependency=dependency.get('dependency'), projects=project)

            tx.run('''
          MATCH (d:dependency {dependency: $dependency})
          SET d.vulnerabilities = $vulnerabilities
          ''',
                   dependency=dependency.get('dependency'), vulnerabilities=dependency.get('vulnerabilities'))

        else:
            tx.run('''
            MERGE (d:dependency {package: $package, dependency: $dependency,
            vulnerabilities: $vulnerabilities, projects: $projects})
            ''', package=dependency.get('package'), dependency=dependency.get('dependency'),
                   vulnerabilities=dependency.get('vulnerabilities'), projects=dependency.get('project'))


def create_vuln_relations():
    tx.run('''   MATCH (d:dependency), (v:vulnerability)
    WHERE v.vulnerability_name IN  d.vulnerabilities

    MERGE(d)-[:VULNERABLE_TO]->(v)
    ''')


def create_project_relations():
    r = tx.run('''
    MATCH (d:dependency), (p:project)
    WHERE p.project_name IN  d.projects
    MERGE (p)-[:USES]->(d)
    ''')

def add_label_colors():
    tx.run('''
    MATCH (v:vulnerability)
    WITH DISTINCT v.severity_desc as severity_desc, collect(DISTINCT v) AS vulns
    CALL apoc.create.addLabels(vulns, [severity_desc]) YIELD node
    RETURN *
    ''')

#if __name__ == "__main__":
    #driver = GraphDatabase.driver(os.environ.get('NEO4J_DB'),
    #                              auth=(os.environ.get('NEO4J_USER'), os.environ.get('NEO4J_PWD')))
    #tx = driver.session()
    #run_cli_scan()
    #driver.close()
