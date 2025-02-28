# SPDX-FileCopyrightText: 2025 BD3D DIGITAL DESIGN (Dorian B.)
#
# SPDX-License-Identifier: GPL-2.0-or-later

# TODO support more operand 
#  - __floordiv__
#  - __modulo__

# TODO implement NexVec
#  - support between vec and vec
#  - vec to float = error, float to vec == possible
#  - dunder operation between NexFloat et NexVec, see how NotImplemented pass the ball to the other class..
#  - Vec itter and slicing? using separate? x,y,z = NexVex should work, x=Vex[0] should work for e in Vec should work as well.
#  - float in vec should work as well

# TODO implement functions
#  - implement a few functions as test, see how a functions that can both work with Vec and Float will work
#    because there will be name collision. perhaps could toy with namespace similar to cpp? Hmm. this would solve it

# TODO implement NexBool
#  - with Nexbool comes comparison operations. == <= ect..

# TODO later 
#  Better errors for user:
#  - need better traceback error for NexError so user can at least now the line where it got all wrong.
#  - it's a bit useless to see a Cannot add 'AnonymousVariable' of type.. with type.. 
#    perhaps just don't tell the user varname if we can print the line?

# TODO later
#  Optimization:
#  - Is the NexFactory bad for performance? these factory are defining classes perhaps 10-15 times per execution
#    and execution can be at very frequent. Perhaps we can initiate the factory at node.init()? If we do that, 
#    let's first check if it's safe to do so. Maybe, storing objects there is not supported. 
#    AS a Reminder: we are storing nodetree objects in there, we'll probably need to only store the nodetree name. & get rid of node_inst.
#  - If we do a constant + Nex + constant + Nex + constant, we'll create 3 constant nodes. Unsure how to mitigate this.
#    ideally we 

# TODO nodes location
# (?) Doing math operation on a value node for the first time should relocate the value node near it's math ope. Note that
# if we optimize the note above, this thought is to be dismissed


import bpy

import traceback


from ..__init__ import dprint
from ..nex.pytonode import convert_pyvar_to_data
from ..nex import nodesetter
from ..utils.node_utils import (
    create_new_nodegroup,
    set_socket_defvalue,
    get_socket,
    get_socket_type,
    set_socket_type,
    create_socket,
    get_socket_from_socketui,
    remove_socket,
    set_socket_label,
    link_sockets,
    create_constant_input,
)


NEXEQUIVALENCE = {
    #inputs
    'inbool':  'NodeSocketBool',
    'inint':   'NodeSocketInt',
    'infloat': 'NodeSocketFloat',
    'invec':   'NodeSocketVector',
    'incol':   'NodeSocketColor',
    'inquat':  'NodeSocketRotation',
    'inmat':   'NodeSocketMatrix',
    #outputs
    'outbool': 'NodeSocketBool',
    'outint':  'NodeSocketInt',
    'outfloat':'NodeSocketFloat',
    'outvec':  'NodeSocketVector',
    'outcol':  'NodeSocketColor',
    'outquat': 'NodeSocketRotation',
    'outmat':  'NodeSocketMatrix',
    }


class NexError(Exception):
    def __init__(self, message):
        super().__init__(message)


class Nex:
    """parent class of all Nex subclasses"""

    _instance_counter = 0 # - Needed to define nxid, see nxid note.
    node_inst = None      # - the node affiliated with this Nex type
    node_tree = None      # - the node.nodetree affiliated with this Nex type
    nxstype = ''          # - the type of socket the Nex type is using
    nxshort = ''          # - the short name of the nex type (for display reasons)

    def __init__(*args, **kwargs):
        nxsock = None  # - The most important part of a NexType, it's association with an output socket!
        nxvname = None # - The name of the variable, if available. High change the variable will be anonymous. Unsure if it's needed to keep this
        nxid = None    # - In order to not constantly rebuild the nodetree, but still update 
                       # some python evaluated values to the nodetree constants (nodes starting with "C|" in the tree)
                       # we need to have some sort of stable id for our nex Instances.
                       # the problem is that these instances can be anonymous. So here i've decided to identify by instance generation count.

    def __repr__(self):
        return f"<{type(self)}{self.nxid} nxvname='{self.nxvname}'  nxsock=`{self.nxsock}` isoutput={self.nxsock.is_output}' socketnode='{self.nxsock.node.name}''{self.nxsock.node.label}'>"


def create_Nex_constant(node_tree, NexType, nodetype:str, value,):
    """Create a new input node (if not already exist) ensure it's default value, then assign to a NexType & return it."""

    new = NexType(manualdef=True)
    tag = f"{new.nxshort}{new.nxid}"

    # create_constant_input() is smart it will create the node only if it doesn't exist, & ensure (new?) values
    newsock = create_constant_input(node_tree, nodetype, value, tag)

    new.nxsock = newsock
    new.nxvname = 'AnonymousVariable'

    return new

def call_Nex_operand(socketfunction, node_tree, NexType, *nexobjs):
    """call the socketfunction related to the operand with sockets of our NexTypes, and return a 
    new NexType from the newly formed socket.
    
    Each new node the socketfunctions will create will be tagged, as it is essential that we don't create & 
    link the nodes if there's no need to do so, as a Nex script can be executed very frequently. 
    
    We tag them using the Nex id and types to ensure uniqueness of our values. If a tag already exists, 
    then it means the nodetree structure must still be good"""

    assert all(isinstance(o, Nex) for o in nexobjs), f"Wrong arguments passed []"
    
    argtags = ",".join([f'{o.nxshort}{o.nxid}' for o in nexobjs])
    tag = f"F|{NexType.nxshort}.{socketfunction.__name__}({argtags})"
    sockets = [o.nxsock for o in nexobjs]

    node = node_tree.nodes.get(tag)
    if (node is None):
        newsock = socketfunction(node_tree, *sockets)
        node = newsock.node
        node.name = node.label = tag
    else:
        newsock = node.outputs[0]

    new = NexType(fromsocket=newsock)
    return new


def NexFactory(factor_customnode_instance, factory_classname:str, factory_outsocktype:str='',):
    """return a nex type, which is simply an overloaded custom type that automatically arrange links and nodes and
    set default values. The nextypes will/should only build the nodetree and links when neccessary"""

    # 888888 88      dP"Yb     db    888888 
    # 88__   88     dP   Yb   dPYb     88   
    # 88""   88  .o Yb   dP  dP__Yb    88   
    # 88     88ood8  YbodP  dP""""Yb   88   

    class NexFloat(Nex):
        
        _instance_counter = 0
        node_inst = factor_customnode_instance
        node_tree = node_inst.node_tree
        nxstype = 'NodeSocketFloat'
        nxshort = 'f'

        def __init__(self, varname='', value=None, fromsocket=None, manualdef=False):

            #create a stable identifier for our NexObject
            self.nxid = NexFloat._instance_counter
            NexFloat._instance_counter += 1

            #on some occation we might want to first initialize this new python object, and define it later (ot get the id)
            if (manualdef):
                return None

            #initialize from a socket?
            if (fromsocket is not None):
                self.nxsock = fromsocket
                self.nxvname = 'AnonymousVariable'
                return None
            
            # Now, define different initialization depending on given value type
            # NOTE to avoid the pitfalls of name resolution within class definitions..

            type_name = type(value).__name__
            match type_name: 

                # a:infloat = anotherinfloat
                case 'NexFloat':
                    raise NexError(f"Invalid use of Inputs. Cannot assign 'SocketInput' to 'SocketInput'.")

                # is user toying with  output? output cannot be reused in any way..
                case 'NexOutput':
                    raise NexError(f"Invalid use of Outputs. Cannot assign 'SocketOutput' to 'SocketInput'.")

                # initial creation by assignation, we need to create a socket type
                case 'int' | 'float' | 'bool':

                    assert varname!='', "NexI Initialization should always define a varname."
                    outsock = get_socket(self.node_tree, in_out='INPUT', socket_name=varname,)
                    assert outsock is not None, f"The socket '{varname}' do not exist in your node inputs."

                    if (value is not None):
                        value = float(value)
                        set_socket_defvalue(self.node_tree, socket=outsock, node=self.node_inst, value=value, in_out='INPUT')

                    self.nxsock = outsock
                    self.nxvname = varname

                # wrong initialization?
                case _:
                    raise NexError(f"SocketTypeError. Cannot assign var '{varname}' of type '{type(value).__name__}' to 'SocketFloat'.")

            print(f'DEBUG: {type(self).__name__}.__init__({value}). Instance:',self)
            return None

        # ---------------------
        # NexFloat Additions

        def __add__(self, other): # self + other
            type_name = type(other).__name__
            match type_name:
                case 'NexFloat':
                    a = self ; b = other
                    socketfunction = nodesetter.add
                case 'int' | 'float' | 'bool': 
                    a = self ; b = create_Nex_constant(self.node_tree, NexFloat, 'ShaderNodeValue', float(other),)
                    socketfunction = nodesetter.add
                case _:
                    raise NexError(f"SocketTypeError. Cannot add '{self.nxvname}' of type 'SocketFloat' to '{type(other).__name__}'.")
            c = call_Nex_operand(socketfunction, self.node_tree, NexFloat, a, b)
            return c

        def __radd__(self, other): # other + self
            # Multiplication is commutative.
            return self.__add__(other)

        # ---------------------
        # NexFloat Subtraction

        def __sub__(self, other): # self - other
            type_name = type(other).__name__
            match type_name:
                case 'NexFloat':
                    a = self ; b = other
                    socketfunction = nodesetter.sub
                case 'int' | 'float' | 'bool':
                    a = self ; b = create_Nex_constant(self.node_tree, NexFloat, 'ShaderNodeValue', float(other),)
                    socketfunction = nodesetter.sub
                case _:
                    raise NexError(f"SocketTypeError. Cannot subtract '{self.nxvname}' of type 'SocketFloat' with '{type(other).__name__}'.")
            c = call_Nex_operand(socketfunction, self.node_tree, NexFloat, a, b)
            return c

        def __rsub__(self, other): # other - self
            type_name = type(other).__name__
            match type_name:
                case 'int' | 'float' | 'bool':
                    b = self ; a = create_Nex_constant(self.node_tree, NexFloat, 'ShaderNodeValue', float(other),)
                    socketfunction = nodesetter.sub
                case _:
                    raise NexError(f"SocketTypeError. Cannot subtract '{type(other).__name__}' with 'SocketFloat'.")
            c = call_Nex_operand(socketfunction, self.node_tree, NexFloat, a, b)
            return c

        # ---------------------
        # NexFloat Multiplication

        def __mul__(self, other): # self * other
            type_name = type(other).__name__
            match type_name:
                case 'NexFloat':
                    a = self ; b = other
                    socketfunction = nodesetter.mult
                case 'int' | 'float' | 'bool':
                    a = self ; b = create_Nex_constant(self.node_tree, NexFloat, 'ShaderNodeValue', float(other),)
                    socketfunction = nodesetter.mult
                case _:
                    raise NexError(f"SocketTypeError. Cannot multiply '{self.nxvname}' of type 'SocketFloat' with '{type(other).__name__}'.")
            c = call_Nex_operand(socketfunction, self.node_tree, NexFloat, a, b)
            return c

        def __rmul__(self, other): # other * self
            # Multiplication is commutative.
            return self.__mul__(other)

        # ---------------------
        # NexFloat True Division

        def __truediv__(self, other): # self / other
            type_name = type(other).__name__
            match type_name:
                case 'NexFloat':
                    a = self ; b = other
                    socketfunction = nodesetter.div
                case 'int' | 'float' | 'bool':
                    a = self ; b = create_Nex_constant(self.node_tree, NexFloat, 'ShaderNodeValue', float(other),)
                    socketfunction = nodesetter.div
                case _:
                    raise NexError(f"SocketTypeError. Cannot divide '{self.nxvname}' of type 'SocketFloat' by '{type(other).__name__}'.")
            c = call_Nex_operand(socketfunction, self.node_tree, NexFloat, a, b)
            return c

        def __rtruediv__(self, other): # other / self
            type_name = type(other).__name__
            match type_name:
                case 'int' | 'float' | 'bool':
                    b = self ; a = create_Nex_constant(self.node_tree, NexFloat, 'ShaderNodeValue', float(other),)
                    socketfunction = nodesetter.div
                case _:
                    raise NexError(f"SocketTypeError. Cannot divide '{type(other).__name__}' by 'SocketFloat'.")
            c = call_Nex_operand(socketfunction, self.node_tree, NexFloat, a, b)
            return c

        # ---------------------
        # NexFloat Power

        def __pow__(self, other): #self ** other
            type_name = type(other).__name__
            match type_name:
                case 'NexFloat':
                    a = self
                    b = other
                    socketfunction = nodesetter.pow
                case 'int' | 'float' | 'bool':
                    a = self
                    b = create_Nex_constant(self.node_tree, NexFloat, 'ShaderNodeValue', float(other),)
                    socketfunction = nodesetter.pow
                case _:
                    raise NexError(f"SocketTypeError. Cannot raise '{self.nxvname}' of type 'SocketFloat' to the power of '{type(other).__name__}'.")
            c = call_Nex_operand(socketfunction, self.node_tree, NexFloat, a, b)
            return c

        def __rpow__(self, other): #other ** self
            type_name = type(other).__name__
            match type_name:
                case 'int' | 'float' | 'bool':
                    b = self ; a = create_Nex_constant(self.node_tree, NexFloat, 'ShaderNodeValue', float(other),)
                    socketfunction = nodesetter.pow
                case _:
                    raise NexError(f"SocketTypeError. Cannot raise '{type(other).__name__}' to the power of 'SocketFloat'.")
            c = call_Nex_operand(socketfunction, self.node_tree, NexFloat, a, b)
            return c

        # ---------------------
        # NexFloat Modulo

        def __mod__(self, other): # self % other
            type_name = type(other).__name__
            match type_name:
                case 'NexFloat':
                    a = self ; b = other
                    socketfunction = nodesetter.mod
                case 'int' | 'float' | 'bool':
                    a = self ; b = create_Nex_constant(self.node_tree, NexFloat, 'ShaderNodeValue', float(other),)
                    socketfunction = nodesetter.mod
                case _:
                    raise NexError(f"SocketTypeError. Cannot compute '{self.nxvname}' of type 'SocketFloat' modulo '{type(other).__name__}'.")
            c = call_Nex_operand(socketfunction, self.node_tree, NexFloat, a, b)
            return c

        def __rmod__(self, other): # other % self
            type_name = type(other).__name__
            match type_name:
                case 'int' | 'float' | 'bool':
                    b = self ; a = create_Nex_constant(self.node_tree, NexFloat, 'ShaderNodeValue', float(other),)
                    socketfunction = nodesetter.mod
                case _:
                    raise NexError(f"SocketTypeError. Cannot compute modulo of '{type(other).__name__}' by 'SocketFloat'.")
            c = call_Nex_operand(socketfunction, self.node_tree, NexFloat, a, b)
            return c

        # ---------------------
        # NexFloat Floor Division

        def __floordiv__(self, other): # self // other
            type_name = type(other).__name__
            match type_name:
                case 'NexFloat':
                    a = self ; b = other
                    socketfunction = nodesetter.floordiv
                case 'int' | 'float' | 'bool':
                    a = self ; b = create_Nex_constant(self.node_tree, NexFloat, 'ShaderNodeValue', float(other),)
                    socketfunction = nodesetter.floordiv
                case _:
                    raise NexError(f"SocketTypeError. Cannot perform floor division on '{self.nxvname}' of type 'SocketFloat' with '{type(other).__name__}'.")
            c = call_Nex_operand(socketfunction, self.node_tree, NexFloat, a, b)
            return c

        def __rfloordiv__(self, other): # other // self
            type_name = type(other).__name__
            match type_name:
                case 'int' | 'float' | 'bool':
                    b = self ; a = create_Nex_constant(self.node_tree, NexFloat, 'ShaderNodeValue', float(other),)
                    socketfunction = nodesetter.floordiv
                case _:
                    raise NexError(f"SocketTypeError. Cannot perform floor division of '{type(other).__name__}' by 'SocketFloat'.")
            c = call_Nex_operand(socketfunction, self.node_tree, NexFloat, a, b)
            return c

        # ---------------------
        # NexFloat Negate

        def __neg__(self): # -self
            c = call_Nex_operand(nodesetter.neg, self.node_tree, NexFloat, self)
            return c
            # minus_one = create_Nex_constant(self.node_tree, NexFloat, 'ShaderNodeValue', -1.0)
            # return minus_one * self

        # ---------------------
        # NexFloat Absolute

        def __abs__(self): # abs(self)
            c = call_Nex_operand(nodesetter.abs, self.node_tree, NexFloat, self)
            return c

    #  dP"Yb  88   88 888888 88""Yb 88   88 888888 
    # dP   Yb 88   88   88   88__dP 88   88   88   
    # Yb   dP Y8   8P   88   88"""  Y8   8P   88   
    #  YbodP  `YbodP'   88   88     `YbodP'   88   
    
    class NexOutput(Nex):
        """A nex output is just a simple linking operation. We only assign to an output.
        After assinging the final output not a lot of other operations are possible"""

        _instance_counter = 0
        node_inst = factor_customnode_instance
        node_tree = node_inst.node_tree
        nxstype = factory_outsocktype
        nxshort = 'o'
        
        outsubtype = nxstype.replace("Node","")

        def __init__(self, varname='', value=0.0):

            assert varname!='', "NexOutput Initialization should always define a varname"
            self.nxvname = varname

            # create a stable identifier for our NexObject
            self.nxid = NexOutput._instance_counter
            NexOutput._instance_counter += 1

            # add a socket to this object
            outsock = get_socket(self.node_tree, in_out='OUTPUT', socket_name=varname,)
            self.nxsock = outsock

            type_name = type(value).__name__
            match type_name:

                # is user toying with  output? output cannot be reused in any way..
                case 'NexOutput':
                    raise NexError(f"Invalid use of Outputs. Cannot assign 'SocketOutput' to 'SocketOutput'.")

                # we link another nextype
                case _ if ('Nex' in type_name):
                    l = link_sockets(value.nxsock, outsock)
                    # we might need to send a refresh signal before checking is_valid property?? if it works, it works
                    if (not l.is_valid):
                        raise NexError(f"SocketTypeError. Cannot assign var '{varname}' of type '{type(value).__name__}' to output socket of type '{self.outsubtype}'.")

                # or we simply output a default python constant value
                case _:
                    newval, _, socktype = convert_pyvar_to_data(value)
                    # just do a try except to see if the var assignment to python is working.. easier.
                    try:
                        set_socket_defvalue(self.node_tree, value=newval, socket=outsock, in_out='OUTPUT',)
                    except Exception as e:
                        raise NexError(f"SocketTypeError. Cannot assign var '{varname}' of type '{type(value).__name__}' to output socket of type '{self.outsubtype}'.")


    # return the class
    ReturnClass = locals().get(factory_classname)
    if (ReturnClass is None):
        raise Exception(f"Type '{factory_classname}' not supported")

    return ReturnClass