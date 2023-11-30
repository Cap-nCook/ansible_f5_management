from ruamel.yaml import YAML
import re
import os
import sys
from ansible.inventory.manager import InventoryManager
from ansible.parsing.dataloader import DataLoader
from ansible.vars.manager import VariableManager


#################Setup YAML object
yaml = YAML(typ='rt')
yaml.representer.ignore_aliases = lambda *args: True

#################Setup to read in INI file to YAML
dl = DataLoader()
im = InventoryManager(loader=dl, sources=['work/qa.ini'])
vm = VariableManager(loader=dl, inventory=im)

list_inv_hosts = im.get_hosts()
host_dict = {}
host_key_list = ['vm_name', 'vm_ipaddress', 'inventory_hostname', 'inventory_hostname_short', 'group_names']
for inv_host in list_inv_hosts:
    var_data = vm.get_vars(host=inv_host) 
    #print(var_data)
    inv_host_short = str.lower(var_data['inventory_hostname_short'])
    host_dict[inv_host_short] = {}
    for var_k, var_value in var_data.items():
        if var_k in  host_key_list:
            host_dict[inv_host_short][var_k] = var_value

# print(host_dict)
# print(im.list_groups())
# my_host = im.get_host('DMSQAGENOUT01*')
# print(my_host)
# print(vm.get_vars(host=my_host))


#################Read in current F5 config from Ansible Gather Facts
with open('work/f5_qa_current_vs_config.yml', 'r') as file:
    data = yaml.load(file)
    #data = yaml.safe_load(file)


f5_app_vs_config_dict = {}
#f5_app_vs_config_dict['f5_app_vs_config'] = {}

net_device_groups_data = data['msg']['ansible_net_device_groups']
net_device_data = data['msg']['ansible_net_devices']
net_irules_data = data['msg']['ansible_net_irules']
net_ltm_pools_data = data['msg']['ansible_net_ltm_pools']
net_nodes_data = data['msg']['ansible_net_nodes']
net_virtual_servers_data = data['msg']['ansible_net_virtual_servers']


###################VS Info Discovery
vs_dict = {}
profiles_dict = {}
vs_status_dict = {}
vs_key_list = ['availability_status', 'default_pool', 'description', 'destination_address', 'destination_port', 'persistence_profile', \
               'enabled', 'irules', 'profiles', 'protocol', 'snat_type', 'source_address', 'status_reason', 'translate_address', 'translate_port']
for list_vs in net_virtual_servers_data:
    #print(list_vs)
    vs_name = list_vs['name']
    vs_dict[vs_name] = {}
    vs_dict[vs_name]['vs_pools'] = {}
    vs_dict[vs_name]['vs_irules'] = []
    for vs_k, vs_value in list_vs.items():
        if vs_k in vs_key_list:
            #print(vs_k, vs_value)
            vs_dict[vs_name][vs_k] = vs_value
            if vs_k == 'availability_status':
                if vs_value in vs_status_dict:
                    vs_status_dict[vs_value]['count'] += 1
                    vs_status_dict[vs_value]['vs'].append(vs_name)
                else:
                    vs_status_dict[vs_value] = {'count': 1, 'vs': [vs_name]}
            if vs_k == 'default_pool':
                default_pool = vs_value.split('/')[2]
                vs_dict[vs_name]['vs_pools'][default_pool] = []
                vs_dict[vs_name]['default_pool_name'] = default_pool
            if vs_k == 'persistence_profile':
                presistance = vs_value.split('/')[2]
                vs_dict[vs_name]['persistence_profile'] = presistance
            if vs_k == 'profiles':
                profilesToStr = '|'.join([str(prof_elem['context']+":"+prof_elem['name']) for prof_elem in vs_value])
                #print(profilesToStr)
                if profilesToStr in profiles_dict:
                   profiles_dict[profilesToStr]['count'] =  profiles_dict[profilesToStr]['count']+1
                   profiles_dict[profilesToStr]['vs'].append(vs_name)
                else:
                   profiles_dict[profilesToStr] = {'count': 1, 'vs': [vs_name]}



###############Irule Info Discovery
irule_dict = {}
for list_irule in net_irules_data:
    # print()
    # print(list_irule['name'])
    # print(list_irule['definition'])
    # print(re.findall(r'(?<=pool\s)[A-Za-z0-9_.-]*', list_irule['definition']))
    irule_pool_list = re.findall(r'(?<=pool\s)[A-Za-z0-9_.-]*', list_irule['definition'])
    while '' in irule_pool_list:
        irule_pool_list.remove('')
    irule_dict[list_irule['name']] = {'pool_instances': irule_pool_list, 'name': list_irule['name'], 'definition': list_irule['definition']}


###############Pool Info Discovery
pool_dict = {}
pool_status_dict = {}
pool_key_list = ['availability_status','active_member_count', 'description', 'enabled_status', 'lb_method', 'member_count', 'members', 'monitors', 'status_reason' ]
for list_pools in net_ltm_pools_data:
    pool_name = list_pools['name']
    pool_dict[pool_name] = {}
    #print()
    #print(pool_name)
    #print(list_pools)
    for pool_k, pool_value in list_pools.items():
        if pool_k in pool_key_list:
            pool_dict[pool_name][pool_k] = pool_value
            # print(pool_k, pool_value)
            if pool_k == 'availability_status':
                pool_status = pool_value
                if pool_value in pool_status_dict:
                    pool_status_dict[pool_value]['count'] += 1
                    pool_status_dict[pool_value]['pool'].append(pool_name)
                else:
                    pool_status_dict[pool_value] = {'count': 1, 'pool': [pool_name]}
            if pool_k == 'monitors':
                pool_dict[pool_name]['monitor_names'] = []
                # print(pool_value)
                for mon in pool_value:
                    # print(mon)
                    pool_mon_name = mon.split('/')[2]
                    pool_dict[pool_name]['monitor_names'].append(pool_mon_name)
            if pool_k == 'members':
                #print(pool_value)
                # print()
                # print(pool_name)
                # print(pool_status)
                pool_dict[pool_name]['group_names'] = []
                pool_dict[pool_name]['member_ports'] = []
                for memb in pool_value:
                    if memb['state'] == 'present' and pool_status == 'available':
                        pool_mem_name = str.lower(memb['name'].split(':', 1)[0])
                        pool_mem_port = int(memb['name'].split(':', 1)[1])
                        if pool_mem_port not in pool_dict[pool_name]['member_ports']:
                            pool_dict[pool_name]['member_ports'].append(pool_mem_port)
                        if pool_mem_name in host_dict:
                            # print(host_dict[pool_mem_name]['group_names'])
                            for g_name in host_dict[pool_mem_name]['group_names']:
                                if g_name not in pool_dict[pool_name]['group_names']:
                                    pool_dict[pool_name]['group_names'].append(g_name)
                        # else:
                        #     print("MEMBER NOT FOUND IN INV "+pool_mem_name)

# print(pool_dict[pool_name])


############F5 Nodes info
node_dict = {}
node_status_dict = {}
node_key_list = ['address']
for list_nodes in net_nodes_data:
    node_name = list_nodes['name']
    node_dict[node_name] = {}
    # print()
    # print(node_name)
    for node_k, node_value in list_nodes.items():
        if node_k in node_key_list:
            node_dict[node_name][node_k] = node_value
            # print(node_k, node_value)



###################Function to write irules defintions to file from F5 config
def write_irule_tcl(irule_file_name, vs_site, file_data):
    basedir = '/home/rarodrigu2/vscode_projects'
    workingdir = basedir+'/work/irules'
    outputdir = workingdir+'/'+vs_site
    if os.path.exists(outputdir):
        with open(outputdir+'/'+irule_file_name, 'w') as file:
            file.write(file_data)
    else:
        os.makedirs(outputdir, mode =0o755)
        with open(outputdir+'/'+irule_file_name, 'w') as file:
            file.write(file_data)

###################Function to clean up env tags on sites/pool names
list_strip_evn_tags = ['qa', 'stg', 'staging', 'perf', 'pa', 'test', 'testing', 'dev']
def strip_evn_tags(clean_name):
    vs_env = ""
    for cln in list_strip_evn_tags:
        check_change = clean_name.replace(cln+'-', '')
        if clean_name != check_change:
            clean_name = check_change
            vs_env = cln
        check_change = clean_name.replace(cln+'.', '.')
        if clean_name != check_change:
            clean_name = check_change
            vs_env = cln
        clean_name = clean_name.replace('-.', '.')
        clean_name = clean_name.replace('..', '.')
    return(clean_name, vs_env)
    

##################### for all 'available' VS definitions test if pool in up and ansible group associated
for k in vs_status_dict['available']['vs']:
    # print()
    if 'irules' in vs_dict[k]:
        # print('IRULE')
        # print(vs_dict[k]['irules'])
        for vs_irule in vs_dict[k]['irules']:
            vs_irule_name = vs_irule.split('/')[2]
            if vs_irule_name not in vs_dict[k]['vs_irules']:
                vs_dict[k]['vs_irules'].append(vs_irule_name)
            # print(vs_irule_name)
            # print(irule_dict[vs_irule_name])
            if 'pool_instances' in irule_dict[vs_irule_name]:
                # print('IRULE POOLS')
                for p in irule_dict[vs_irule_name]['pool_instances']:
                    if p != "" and p not in vs_dict[k]['vs_pools'] and pool_dict[p]['availability_status'] != 'offline':
                        vs_dict[k]['vs_pools'][p] = []
    for vs_p in vs_dict[k]['vs_pools']:
        # print(vs_p)
        # print(pool_dict[vs_p]['group_names'])
        # print(pool_dict[vs_p]['availability_status'])
        for g_name in pool_dict[vs_p]['group_names']:
            if g_name != "" and g_name not in vs_dict[k]['vs_pools'][vs_p]:
                vs_dict[k]['vs_pools'][vs_p].append(g_name)
    # print()
    # print('VIP')
    # print(k)
    # print(vs_dict[k])
    vs_dict[k]['cln_vs_name'] = strip_evn_tags(k)[0]
    vs_obj_env = strip_evn_tags(k)[1]
    # print(vs_obj_env)
    if vs_obj_env == '':
        vs_obj_env = 'qa'

    vs_site = vs_dict[k]['cln_vs_name'].split('_')[0]
    vs_site_hostname = vs_site.split('.')[0]
    vs_domain_name = vs_site.replace(vs_site_hostname+'.', '') 
    

    if vs_site_hostname not in f5_app_vs_config_dict:
        f5_app_vs_config_dict[vs_site_hostname] = {}
        # f5_app_vs_config_dict['f5_app_vs_config'][vs_site_hostname]['default_vs'] = {}
        
    f5_app_vs_config = f5_app_vs_config_dict[vs_site_hostname]

    if 'legacy_name' not in f5_app_vs_config:
        f5_app_vs_config['legacy_name'] = []
    if k not in f5_app_vs_config['legacy_name']:
        f5_app_vs_config['legacy_name'].append(k)

    f5_app_vs_config['site_hostname'] = vs_site_hostname
    f5_app_vs_config['f5_domain'] = 'pub'

    if 'domain' not in f5_app_vs_config:
        f5_app_vs_config['domain'] = []
    if vs_domain_name not in f5_app_vs_config['domain']:
        f5_app_vs_config['domain'].append(vs_domain_name)


    if 'destination_address' not in f5_app_vs_config: 
        f5_app_vs_config['destination_address'] = {}
    f5_app_vs_config['destination_address'][vs_obj_env] = vs_dict[k]['destination_address']

    if 'destination_port' not in f5_app_vs_config: 
        f5_app_vs_config['destination_port'] = {}
    f5_app_vs_config['destination_port'][vs_obj_env] = vs_dict[k]['destination_port']

    if 'persistence_profile' not in f5_app_vs_config: 
        f5_app_vs_config['persistence_profile'] = {}
    if 'persistence_profile' in vs_dict[k]:
        f5_app_vs_config['persistence_profile'][vs_obj_env] = vs_dict[k]['persistence_profile']

    if 'irules' in vs_dict[k]:
        # print(vs_dict[k]['irules'])
        f5_app_vs_config['irules'] = {}
        for vs_i in vs_dict[k]['vs_irules']:
            f5_app_vs_config['irules'][vs_i] = {}
            f5_app_vs_config_irule = f5_app_vs_config['irules'][vs_i]
            f5_app_vs_config_irule['name'] = vs_i
            f5_app_vs_config_irule['template'] = vs_site+'/'+vs_i+'.tcl'
            if 'sites' not in f5_app_vs_config_irule: 
                f5_app_vs_config_irule['sites'] = []
            if vs_obj_env not in f5_app_vs_config_irule['sites']:
                f5_app_vs_config_irule['sites'].append(vs_obj_env)
            
            #Generate TCL file to upload to github
            write_irule_tcl(vs_i+'.tcl', vs_site, irule_dict[vs_i]['definition'])
    else:
        f5_app_vs_config['irules'] = {}

    if 'pools' not in f5_app_vs_config: 
        f5_app_vs_config['pools'] = {}
    for vs_p in vs_dict[k]['vs_pools']:
        # print(pool_dict[vs_p])
        pool_tag = strip_evn_tags(vs_p)[0]
        vs_obj_env = strip_evn_tags(vs_p)[1]
        if vs_obj_env == '':
            vs_obj_env = 'qa'
        if 'default_pool_name' in vs_dict[k]:
            if vs_p == vs_dict[k]['default_pool_name']:
                pool_tag = 'default_pool'
        if pool_tag not in f5_app_vs_config['pools']: 
            f5_app_vs_config['pools'][pool_tag] = {}

        f5_app_vs_config_pool = f5_app_vs_config['pools'][pool_tag]

        if 'legacy_name' not in f5_app_vs_config_pool:
            f5_app_vs_config_pool['legacy_name'] = []
        if vs_p not in f5_app_vs_config_pool['legacy_name']:
            f5_app_vs_config_pool['legacy_name'].append(vs_p)

        f5_app_vs_config_pool['name'] = vs_site
        f5_app_vs_config_pool['lb_method'] = pool_dict[vs_p]['lb_method']
        f5_app_vs_config_pool['node_label'] = ""
        if len(pool_dict[vs_p]['member_ports']) == 1:
            f5_app_vs_config_pool['pool_label_port'] = pool_dict[vs_p]['member_ports'][0]
        else:
            f5_app_vs_config_pool['pool_label_port'] = "MULTIPLE_PORTS"  
        f5_app_vs_config_pool['service_port'] = pool_dict[vs_p]['member_ports']
        if 'monitor_names' in pool_dict[vs_p]:
            f5_app_vs_config_pool['monitor'] = pool_dict[vs_p]['monitor_names']
        else:
            f5_app_vs_config_pool['monitor'] = 'MONITOR_MISSING'
        
        
        if 'sites' not in f5_app_vs_config_pool: 
            f5_app_vs_config_pool['sites'] = []
        if vs_obj_env not in f5_app_vs_config_pool['sites']:
            f5_app_vs_config_pool['sites'].append(vs_obj_env)

        if 'inv_group' not in f5_app_vs_config_pool: 
            f5_app_vs_config_pool['inv_group'] = {}
        f5_app_vs_config_pool['inv_group'][vs_obj_env] = pool_dict[vs_p]['group_names']
    # print()
    # print(f5_app_vs_config['site_hostname'])
    # print(f5_app_vs_config)

yaml.dump(f5_app_vs_config_dict, sys.stdout)


# for k, v in vs_dict.items():
#     print()
#     print(k)
#     print(v)

# for k, v in profiles_dict.items():
#     print()
#     print(k)
#     print(v)

# print(irule_dict)

# for k, v in pool_dict.items():
#     print()
#     print(k)
#     print(v)

# for k, v in pool_status_dict.items():
#     print()
#     print(k)
#     print(v)

# for k, v in node_dict.items():
#     print()
#     print(k)
#     print(v)



