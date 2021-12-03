# This is a universal architect calculator module
# Version 0.2
# Released to the Public Domain by Paul Spooner

# INFILE is the specification to solve
INFILE = "Specification.txt"
# MARGIN is how much to try to overshoot.
# larger will (generally) solve faster
MARGIN = 1.25

# toggles in-progress printouts
DEBUG = False #True #
VERBOSE = True #False #
ERRORS = True #False #

# how many solver loops to run before giving up
MAXLOOPS = 105

# if the child item is not a node, treat it as a resource

#########################################################
# Code Below. Edit at your own risk.
#########################################################

if MARGIN < 1:
    if VERBOSE: print("The MARGIN value you set was too low. Setting it to 1")
    MARGIN = 1


AllNodes = {}
SolveNodeNames = []
NestedNodeNames = []
StaticNodeNames = []
AllResources = {}
#'petals': [[-2.1, 'petal eater'],
# [5.0, 'Potted Plant'], [20.0, 'Wildflower']]
Productions = {} # same as AllResources, but positive values only
COMMENT = ''
commflaglen = 0
NODESTART = ''
nodeflaglen = 0


#some functions to use as hash keys
def Local():return
def ChildProduction():return
def ChildConsumption():return
def Net():return
def ContainsNodes():return
def SolveSet():return


unlabelednum = 0
unlabeledmessage = "unlabeled node {} contains {} and has been discarded"
def addnode(curnode, curname):
    '''Add curnode to AllNodes
only used to parse the spec file'''
    global AllNodes, unlabelednum
    if len(curname) == 0:
        if unlabelednum and VERBOSE:
            print(unlabeledmessage.format(unlabelednum,curnode))
        unlabelednum += 1
        return
    NewNode = {}
    NewNode[Net] = {}
    NewNode[Local] = curnode
    AllNodes[curname] = NewNode
    # don't bother adding zero contents nodes to the solve list
    if len(curnode) == 0:
        return
    solveit = True
    for i in curnode.values():
        if i >= 0:
            solveit = False
            break
    if solveit:
        SolveNodeNames.append(curname)
    return


def addorappend(thisdict, key, value):
    '''add a numeric value to thisdict'''
    if key not in thisdict: thisdict[key] = value
    else: thisdict[key] += value
    return

def appendtosublist(thisdict, key, item):
    '''append item to the list stored in thisdict'''
    if key not in thisdict: thisdict[key] = []
    thisdict[key].append(item)

# the dictionary keys to parse in order to calculate
# the net resource production
NETKEYS = (ChildProduction, ChildConsumption)
def calcnet(thisnode):
    '''add up all the values from NETKEYS to Net'''
    newnet = {}
    for setkey in NETKEYS:
        thisdict = thisnode[setkey]
        # update to the new values
        for thiskey in thisdict:
            if thiskey in AllNodes:
                if ERRORS:
                    estr = ("How did {} "
                            + "get into {}? "
                            + "That should never happen!")
                    print(estr.format(thiskey, setkey))
                continue
            resourcename = thiskey
            qty = thisdict[resourcename]
            addorappend(newnet, resourcename, qty)
    thisnode[Net] = newnet
    return

def grossentry(otherqty, item, thisnode):
    if otherqty > 0:
        addorappend(thisnode[ChildProduction], item, otherqty)
    elif otherqty < 0:
        addorappend(thisnode[ChildConsumption], item, otherqty)

def calcgross(thisnode):
    '''compute the gross values from Local'''
    if not thisnode[ContainsNodes]: return
    LocalItems = thisnode[Local]
    thisnode[ChildProduction] = {}
    thisnode[ChildConsumption] = {}
    for item in LocalItems:
        othernodeqty = LocalItems[item]
        if item not in AllNodes:
            grossentry(othernodeqty, item, thisnode)
            continue
        othernode = AllNodes[item]
        othernodenet = othernode[Net]
        for resourcekey in othernodenet:
            if resourcekey in AllNodes:
                if ERRORS:
                    estr = ("How did {} "
                            + "get into {}[Net]? "
                            + "That should never happen!")
                    print(estr.format(resourcekey, item))
                continue
            resourcevalue = othernodenet[resourcekey] * othernodeqty
            grossentry(resourcevalue, resourcekey, thisnode)
    return

def inithasnodes(thisnodename):
    '''initalize nodes that contain other nodes'''
    global NestedNodeNames
    thisnode = AllNodes[thisnodename]
    thisnode[ContainsNodes] = True
    thisnode[ChildProduction] = {}
    thisnode[ChildConsumption] = {}
    if thisnodename not in NestedNodeNames:
        NestedNodeNames.append(thisnodename)
    return

def addresources(thisnodename):
    '''add the resources this node produces to the resource lists'''
    global AllResources
    global Productions
    thisnode = AllNodes[thisnodename]
    netitems = thisnode[Net]
    for resource in netitems:
        qty = netitems[resource]
        if resource not in AllResources:
            AllResources[resource] = []
        if (([qty, thisnodename] in AllResources[resource]) and ERRORS):
            errorstring = ("How did {} "
                           + "try to add {} "
                           + "when it's already in AllResources?")
            print(errorstring.format(thisnodename, resource))
            raise
        AllResources[resource].append([qty, thisnodename])
        AllResources[resource].sort()
        if qty <= 0: continue
        if resource not in Productions:
            Productions[resource] = []
        Productions[resource].append([qty, thisnodename])
        Productions[resource].sort(reverse=True)

def removeresources(thisnodename):
    '''remove the resources this node produces from the resource lists'''
    global AllResources
    global Productions
    thisnode = AllNodes[thisnodename]
    netitems = thisnode[Net]
    for resource in netitems:
        if resource not in AllResources:
            if ERRORS:
                errorstring = ("How did {} "
                               + "have {} "
                               + "without AllResources knowing about it?")
                print(errorstring.format(thisnodename, resource))
            continue
        qty = netitems[resource]
        AllResources[resource].pop(
            AllResources[resource].index(
                [qty, thisnodename]))
        if qty <= 0: continue
        if resource not in Productions:
            Productions[resource] = []
            if ERRORS:
                errorstring = ("How did {} "
                               + "produce {} "
                               + "without Productions knowing about it?")
                print(errorstring.format(thisnodename, resource))
            continue
        Productions[resource].pop(
            Productions[resource].index(
                [qty, thisnodename]))

def nestednodeupdate(NodesToUpdate):
    '''update nodes and return a list of nodes that need to be updated again'''
    if DEBUG: print("updating",len(NodesToUpdate),"nodes")
    # update the nested node relationship
    for recalcnodename in NodesToUpdate:
        recalcnode = AllNodes[recalcnodename]
        if recalcnodename not in SolveNodeNames:
            removeresources(recalcnodename)
        calcgross(recalcnode)
        calcnet(recalcnode)
        if recalcnodename not in SolveNodeNames:
            addresources(recalcnodename)
    NodesUpdatedLastTime = NodesToUpdate[:]
    NodesToUpdate = []
    for nodename in NestedNodeNames:
        node = AllNodes[nodename]
        for item in node[Local]:
            if ((item in NodesUpdatedLastTime)
                and nodename not in NodesToUpdate):
                NodesToUpdate.append(nodename)
    return NodesToUpdate

# now we start actually processing stuff

f = open(INFILE)
data = f.read()
f.close()
lines = data.split('\n')
del(data)

curnode = {}
curname = ''

for line in lines:
    line = line.strip()
    if len(line) == 0: continue
    if COMMENT == '':
        COMMENT = line
        commflaglen = len(COMMENT)
        if VERBOSE: print("the comment string has been \
identified as '{}'".format(COMMENT))
        continue
    if line[:commflaglen] == COMMENT: continue
    if NODESTART == '':
        NODESTART = line
        nodeflaglen = len(NODESTART)
        if VERBOSE: print("the node string has been \
identified as '{}'".format(NODESTART))
        continue
    if line[:nodeflaglen] == NODESTART:
        # file the existing node
        addnode(curnode, curname)
        curname = line[nodeflaglen:].strip()
        curnode = {}
        continue
    things = line.split()
    name = ' '.join(things[:-1])
    qty = float(things[-1])
    curnode[name] = qty
del(lines)

# wrap up the last node
addnode(curnode, curname)
if VERBOSE:
    print('all nodes are:')
    for i in AllNodes:
        print(i, AllNodes[i][Local])


# initialize nesting flags
for thisnodename in AllNodes:
    thisnode = AllNodes[thisnodename]
    thisnode[ContainsNodes] = False
    localitems = thisnode[Local]
    for item in thisnode[Local]:
        if item in AllNodes:
            if thisnodename in SolveNodeNames:
                localitems[item] = max(localitems[item],
                                       -localitems[item])
                # invert solve-for node values in Local,
                # since this is simpler than adding them
                # back and doing the math and keeping
                # track of everything
            if ((not thisnode[ContainsNodes])
                and (thisnodename not in SolveNodeNames)):
                inithasnodes(thisnodename)
            continue
    if (not thisnode[ContainsNodes]):
        StaticNodeNames.append(thisnodename)

for solvenodename in SolveNodeNames:
    inithasnodes(solvenodename)
    # we will need the SolveSet list later
    AllNodes[solvenodename][SolveSet] = []

# need to update all nodes
# first the static nodes
for thisnodename in StaticNodeNames:
    thisnode = AllNodes[thisnodename]
    thisnode[Net] = thisnode[Local]
    addresources(thisnodename)

# then the dynamic nodes
# check now for cyclic dependency
NodesToUpdate = NestedNodeNames[:]
maxcycles = len(NestedNodeNames)
cycledetected = False
i = 0
while len(NodesToUpdate):
    if i > maxcycles:
        cycledetected = True
        print("Cycle detected, involving the following nodes")
        print(NodesToUpdate)
        print('aborting')
        break
    NodesToUpdate = nestednodeupdate(NodesToUpdate)
    i += 1

if VERBOSE: print('solving for:\n', SolveNodeNames)

iterations = 0

NodesToUpdate = SolveNodeNames[:]
while len(NodesToUpdate):
    if cycledetected: break
    if DEBUG: print('calc iter',iterations)
    # update the nested node relationship
    RecurseTheseNodes = NodesToUpdate[:]
    while len(RecurseTheseNodes):
        RecurseTheseNodes = nestednodeupdate(RecurseTheseNodes)
    # update the resource deficit,
    # single pass
    NextNodestoUpdate = []
    for solvenodename in NodesToUpdate:
        solvenode = AllNodes[solvenodename]
        NetResult = solvenode[Net]
        LocalNodes = solvenode[Local]
        CurrentSolutionList = solvenode[SolveSet]
        # [Resource Net Value, resource name, {node names:quantities}]
        
        for resource in NetResult:
            # check for deficits
            qty = NetResult[resource]
            if (qty >= 0): continue
            # Does have a deficiet in this resource
            # build an index of all the resources we've tried to solve
            resource_solutions = [i[1] for i in CurrentSolutionList]
            # Add it to the solutions list
            if resource not in resource_solutions:
                CurrentSolutionList.append([qty, resource, {}])
            else:
                idx = resource_solutions.index(resource)
                CurrentSolutionList[idx][0] = qty
            if solvenodename not in NextNodestoUpdate:
                NextNodestoUpdate.append(solvenodename)
        if solvenodename not in NextNodestoUpdate:
            # this node is already balanced
            # we will still check it again, in case it becomes
            # unbalanced later
            continue
        
        CurrentSolutionList.sort()
        if DEBUG: print('current solution', CurrentSolutionList)
        # CurrentSolutionList now has the latest deficits,
        # and the largest deficits are at the front
        # Just solve for the largest deficit this time
        solutiondata = CurrentSolutionList[0]
        oldresourcenet, resource, NodesToTry = solutiondata
        # reset the solution for this resource
        # just so we aren't working from old data
        for nodename in NodesToTry:
            nodeqty = NodesToTry[nodename]
            LocalNodes[nodename] -= nodeqty
        #solutiondata[2] = {}
        # re-calc
        calcgross(solvenode)
        # I used to recalc the net values as well, but that isn't
        # necessary at this stage. They will get
        # regenerated when the recursive calculator runs
        # at the begining of the next iteration
        
        # Gather the gross values
        if resource in solvenode[ChildProduction]:
            grossproduction = solvenode[ChildProduction][resource]
        else: grossproduction = 0
        if resource in solvenode[ChildConsumption]:
            grossconsumption = solvenode[ChildConsumption][resource]
        else: grossconsumption = 0
        # consumption is all negative values
        currentresourcenet = grossproduction + grossconsumption
        if oldresourcenet < currentresourcenet and ERRORS:
            print(solvenodename,resource,
                  "is solving sideways! Iter", iterations)
            print(oldresourcenet, currentresourcenet)
            print(solutiondata)
            print(LocalNodes)
            break
        solutiondata[2] = {}
        
        availablesources = Productions[resource]
        thispassproduction = grossproduction
        minproduction = - grossconsumption
        upperproduction = minproduction * MARGIN
        for idx, candidate in enumerate(availablesources):
            candidateproduction, candidatenode = candidate
            #Add as many as fit
            CurrentNet = minproduction - thispassproduction
            needed = 1 + CurrentNet//candidateproduction
            productioncheck = candidateproduction*needed + thispassproduction
            if productioncheck > upperproduction:
                needed -= 1
            if needed < 0 and ERRORS:
                print(solvenodename,resource,
                      "is solving Upside down! Iter", iterations)
                print(availablesources)
                print(idx, candidate, CurrentNet, needed, productioncheck)
                break
            if needed == 0: continue
            thispassproduction += candidateproduction*needed
            addorappend(solutiondata[2], candidatenode, needed)
            if thispassproduction >= minproduction: break
        # perhaps we're still net negative. fix the corner case
        if thispassproduction < minproduction:
            candidateproduction, candidatenode = availablesources[-1]
            thispassproduction += candidateproduction
            addorappend(solutiondata[2], candidatenode, 1)
            if DEBUG: print(thispassproduction,
                              minproduction, upperproduction)
        solutiondata[0] = thispassproduction + grossconsumption
        if DEBUG: print(CurrentSolutionList)
        for nodename in solutiondata[2]:
            # commit the solution to the "LocalNodes" data
            nodeqty = solutiondata[2][nodename]
            addorappend(LocalNodes,nodename,nodeqty)
    iterations += 1
    NodesToUpdate = NextNodestoUpdate
    if iterations > MAXLOOPS:
        if ERRORS: print("exceeded iteration limit")
        break

for solvenodename in SolveNodeNames:
    if cycledetected: break
    solvenode = AllNodes[solvenodename]
    OUTFILE = solvenodename + ".txt"
    f = open(OUTFILE, 'w')
    f.write(COMMENT+'\n')
    f.write(COMMENT+" generated in "+str(iterations)+" iterations.\n")
    f.write(NODESTART+'\n')
    f.write(COMMENT+' Originally calculated from '+INFILE+'\n')
    f.write(NODESTART+solvenodename+'\n')
    NetDict = solvenode[Net]
    for resource in NetDict:
        value = NetDict[resource]
        f.write(resource+' '+str(value)+'\n')
        gpfx = COMMENT+' '+resource
        if resource in solvenode[ChildProduction]:
            f.write(gpfx+' generated '
                    +str(solvenode[ChildProduction][resource])+'\n')
        if resource in solvenode[ChildConsumption]:
            f.write(gpfx+' consumed '
                    +str(solvenode[ChildConsumption][resource])+'\n')
    LocalDict = solvenode[Local]
    f.write(COMMENT+' All local nodes and resources are as follows:\n')
    for thing in LocalDict:
        value = LocalDict[thing]
        f.write(COMMENT+' '+thing+' '+str(value)+'\n')
    f.write(COMMENT+" node results for "+solvenodename+' complete')
    f.close()
    
# Check for runaway?
if VERBOSE: print("Done in",iterations)
if DEBUG: input("press Enter to close")
