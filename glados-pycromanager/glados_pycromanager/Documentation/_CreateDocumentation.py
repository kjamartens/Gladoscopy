
"""Program to generate `Docs` using `pdoc3` and crate a central `index.html`"""

import inspect
import os
from pathlib import Path

from pdoc import _render_template, import_module


def generate_docs_and_central_index(modules_to_process: list[str],path) -> None:
    """Method to generate `docs` folder with central `index.html`

    Args:
        modules_to_process (list[str]): List of modules to process
    """


    modules = [import_module(module, reload=True) for module in modules_to_process]

    # Generate the docs for each module under docs folder
    command = f'pdoc --html --skip-errors --force --output-dir {path} {" ".join(modules_to_process)}'
    os.system(command=command)

    # # Create a single base `index.html`
    # with open(Path(path, "index.html"), "w", encoding="utf-8") as index:
    #     index.write(_render_template("/html.mako", modules=sorted((module.__name__, inspect.getdoc(module)) for module in modules))) #type:ignore


if __name__ == "__main__":
    path='glados-pycromanager/glados_pycromanager/Documentation'
    # Update this as per your source
    module_list = ["glados-pycromanager/glados_pycromanager/GUI/AnalysisClass.py","glados-pycromanager/glados_pycromanager/GUI/GUI_napari.py","glados-pycromanager/glados_pycromanager/GUI/FlowChart_dockWidgets.py","glados-pycromanager/glados_pycromanager/GUI/MDAGlados.py","glados-pycromanager/glados_pycromanager/GUI/MMcontrols.py","glados-pycromanager/glados_pycromanager/GUI/napariGlados.py","glados-pycromanager/glados_pycromanager/GUI/napariHelperFunctions.py","glados-pycromanager/glados_pycromanager/GUI/sharedFunctions.py","glados-pycromanager/glados_pycromanager/GUI/utils.py"]
    generate_docs_and_central_index(module_list,path=path)
    
    
    #Fuck it, we'll create our own html
    modules = [import_module(module, reload=True) for module in module_list]
    modules=sorted((module.__name__, inspect.getdoc(module)) for module in modules)
    #Change all links to add .html, so they work...
    
    
    html_content = """<html>
    
    <head>
    <meta charset="utf-8">
    <meta name="viewport" content="width=device-width, initial-scale=1, minimum-scale=1" />
    <meta name="generator" content="pdoc 0.10.0" />



        <title>Python module list</title>
        <meta name="description" content="A list of documented Python modules." />

    <link rel="preload stylesheet" as="style" href="https://cdnjs.cloudflare.com/ajax/libs/10up-sanitize.css/11.0.1/sanitize.min.css" integrity="sha256-PK9q560IAAa6WVRRh76LtCaI8pjTJ2z11v0miyNNjrs=" crossorigin>
    <link rel="preload stylesheet" as="style" href="https://cdnjs.cloudflare.com/ajax/libs/10up-sanitize.css/11.0.1/typography.min.css" integrity="sha256-7l/o7C8jubJiy74VsKTidCy1yBkRtiUGbVkYBylBqUg=" crossorigin>
        <link rel="stylesheet preload" as="style" href="https://cdnjs.cloudflare.com/ajax/libs/highlight.js/10.1.1/styles/github.min.css" crossorigin>

    
    <style>:root{--highlight-color:#fe9}.flex{display:flex !important}body{line-height:1.5em}#content{padding:20px}#sidebar{padding:30px;overflow:hidden}#sidebar > *:last-child{margin-bottom:2cm}.http-server-breadcrumbs{font-size:130%;margin:0 0 15px 0}#footer{font-size:.75em;padding:5px 30px;border-top:1px solid #ddd;text-align:right}#footer p{margin:0 0 0 1em;display:inline-block}#footer p:last-child{margin-right:30px}h1,h2,h3,h4,h5{font-weight:300}h1{font-size:2.5em;line-height:1.1em}h2{font-size:1.75em;margin:1em 0 .50em 0}h3{font-size:1.4em;margin:25px 0 10px 0}h4{margin:0;font-size:105%}h1:target,h2:target,h3:target,h4:target,h5:target,h6:target{background:var(--highlight-color);padding:.2em 0}a{color:#058;text-decoration:none;transition:color .3s ease-in-out}a:hover{color:#e82}.title code{font-weight:bold}h2[id^="header-"]{margin-top:2em}.ident{color:#900}pre code{background:#f8f8f8;font-size:.8em;line-height:1.4em}code{background:#f2f2f1;padding:1px 4px;overflow-wrap:break-word}h1 code{background:transparent}pre{background:#f8f8f8;border:0;border-top:1px solid #ccc;border-bottom:1px solid #ccc;margin:1em 0;padding:1ex}#http-server-module-list{display:flex;flex-flow:column}#http-server-module-list div{display:flex}#http-server-module-list dt{min-width:10%}#http-server-module-list p{margin-top:0}.toc ul,#index{list-style-type:none;margin:0;padding:0}#index code{background:transparent}#index h3{border-bottom:1px solid #ddd}#index ul{padding:0}#index h4{margin-top:.6em;font-weight:bold}@media (min-width:200ex){#index .two-column{column-count:2}}@media (min-width:300ex){#index .two-column{column-count:3}}dl{margin-bottom:2em}dl dl:last-child{margin-bottom:4em}dd{margin:0 0 1em 3em}#header-classes + dl > dd{margin-bottom:3em}dd dd{margin-left:2em}dd p{margin:10px 0}.name{background:#eee;font-weight:bold;font-size:.85em;padding:5px 10px;display:inline-block;min-width:40%}.name:hover{background:#e0e0e0}dt:target .name{background:var(--highlight-color)}.name > span:first-child{white-space:nowrap}.name.class > span:nth-child(2){margin-left:.4em}.inherited{color:#999;border-left:5px solid #eee;padding-left:1em}.inheritance em{font-style:normal;font-weight:bold}.desc h2{font-weight:400;font-size:1.25em}.desc h3{font-size:1em}.desc dt code{background:inherit}.source summary,.git-link-div{color:#666;text-align:right;font-weight:400;font-size:.8em;text-transform:uppercase}.source summary > *{white-space:nowrap;cursor:pointer}.git-link{color:inherit;margin-left:1em}.source pre{max-height:500px;overflow:auto;margin:0}.source pre code{font-size:12px;overflow:visible}.hlist{list-style:none}.hlist li{display:inline}.hlist li:after{content:',\2002'}.hlist li:last-child:after{content:none}.hlist .hlist{display:inline;padding-left:1em}img{max-width:100%}td{padding:0 .5em}.admonition{padding:.1em .5em;margin-bottom:1em}.admonition-title{font-weight:bold}.admonition.note,.admonition.info,.admonition.important{background:#aef}.admonition.todo,.admonition.versionadded,.admonition.tip,.admonition.hint{background:#dfd}.admonition.warning,.admonition.versionchanged,.admonition.deprecated{background:#fd4}.admonition.error,.admonition.danger,.admonition.caution{background:lightpink}</style>




        <script defer src="https://cdnjs.cloudflare.com/ajax/libs/highlight.js/10.1.1/highlight.min.js" integrity="sha256-Uv3H6lx7dJmRfRvH8TH6kJD1TSK1aFcwgx+mdg3epi8=" crossorigin></script>
        <script>window.addEventListener('DOMContentLoaded', () => hljs.initHighlighting())</script>

    
    </head>
    <body>
    
    <main>
    <article id = 'content'>
    <h1> Module list </h1>
    <table style="border-collapse: collapse;">
    
    """
    for id in range(len(modules)):
        moduleName = modules[id][0]
        moduleInfo = modules[id][1]
        if moduleInfo != None:
            moduleInfo = moduleInfo.replace('\n', '<br>')
        html_content += f"<tr><td style='padding: 20px; border: 1px solid lightgray; width: 20%; text-align: right;'><a href='{moduleName}.html'>{moduleName}</a></td>"
        html_content += f"<td style='padding: 10px; border: 1px solid lightgray; width: 80%;'>{moduleInfo}</td>"
        html_content+= "</tr>"
    html_content += "</table></article></body></html>"
        

    # Store the modified HTML
    with open(path+'/index.html', 'w', encoding='utf-8') as file:
        file.write(html_content)
    
    print('Documentation created!')
