import os

import numpy as np
import tensorflow as tf
from math_functions.c_to_r_mat import CtoRMat
from custom_kernels.gradients.matexp_grad_v3 import *
import os

class TensorflowState:
    
    def __init__(self,sys_para,use_gpu = True):
        self.sys_para = sys_para
	this_dir = os.path.dirname(__file__)
	user_ops_path = os.path.join(this_dir,'../custom_kernels/build')

	if use_gpu:
		kernel_filename = 'cuda_matexp_v4.so'
	else:
		kernel_filename = 'matrix_exp.so'	

	self.matrix_exp_module = tf.load_op_library(os.path.join(user_ops_path,kernel_filename))        

    def init_variables(self):
        self.tf_identity = tf.constant(self.sys_para.identity,dtype=tf.float32)
        self.tf_neg_i = tf.constant(CtoRMat(-1j*self.sys_para.identity_c),dtype=tf.float32)
        self.tf_one_minus_gaussian_evelop = tf.constant(self.sys_para.one_minus_gauss,dtype=tf.float32)
        
        
    def init_tf_vectors(self):
        self.tf_initial_vectors=[]
        for initial_vector in self.sys_para.initial_vectors:
            tf_initial_vector = tf.constant(initial_vector,dtype=tf.float32)
            self.tf_initial_vectors.append(tf_initial_vector)
    
    def init_tf_states(self):
        #tf initial and target states
        self.tf_initial_state = tf.constant(self.sys_para.initial_state,dtype=tf.float32)
        self.tf_target_state = tf.constant(self.sys_para.target_state,dtype=tf.float32)
        print "State initialized."
        
        
    def init_tf_ops(self):
        #flat operators for control Hamiltonian 
        i_array = np.eye(2*self.sys_para.state_num)
        op_matrix_I=i_array.tolist()
        self.I_flat = [item for sublist in op_matrix_I  for item in sublist]
        self.H0_flat = [item for sublist in self.sys_para.H0  for item in sublist]
        
        self.flat_ops = []
        for op in self.sys_para.ops:
            flat_op = [item for sublist in op for item in sublist]
            self.flat_ops.append(flat_op)
            
        print "Operators initialized."
        
    def get_j(self,l, Dt):
        dt=self.sys_para.dt
        jj=np.floor((l*dt-0.5*Dt)/Dt)
        return jj
    
    
            
    def transfer_fn(self,xy):
        
        indices=[]
        values=[]
        shape=[self.sys_para.steps,self.sys_para.control_steps]
        dt=self.sys_para.dt
        Dt=self.sys_para.Dt
    
    # Cubic Splines
        for ll in range (self.sys_para.steps):
            jj=self.get_j(ll, Dt)
            tao= ll*dt - jj*Dt - 0.5*Dt
            if jj >= 1:
                indices.append([int(ll),int(jj-1)])
                temp= -(tao/(2*Dt))*((tao/Dt)-1)**2
                values.append(temp)
                
            if jj >= 0:
                indices.append([int(ll),int(jj)])
                temp= 1+((3*tao**3)/(2*Dt**3))-((5*tao**2)/(2*Dt**2))
                values.append(temp)
                
            if jj+1 <= self.sys_para.control_steps-1:
                indices.append([int(ll),int(jj+1)])
                temp= ((tao)/(2*Dt))+((4*tao**2)/(2*Dt**2))-((3*tao**3)/(2*Dt**3))
                values.append(temp)
               
            if jj+2 <= self.sys_para.control_steps-1:
                indices.append([int(ll),int(jj+2)])
                temp= ((tao**3)/(2*Dt**3))-((tao**2)/(2*Dt**2))
                values.append(temp)
                
            
        T1=tf.SparseTensor(indices, values, shape)  
        T2=tf.sparse_reorder(T1)
        T=tf.sparse_tensor_to_dense(T2)
        temp1 = tf.matmul(T,tf.reshape(xy[0,:],[self.sys_para.control_steps,1]))
        temp2 = tf.matmul(T,tf.reshape(xy[1,:],[self.sys_para.control_steps,1]))
        xys=tf.concat(1,[temp1,temp2])
        return tf.transpose(xys)

    def transfer_fn_general(self,w,steps):
        
        indices=[]
        values=[]
        shape=[self.sys_para.steps,steps]
        dt=self.sys_para.dt
        Dt=self.sys_para.total_time/steps
    
    # Cubic Splines
        for ll in range (self.sys_para.steps):
            jj=self.get_j(ll,Dt)
            tao= ll*dt - jj*Dt - 0.5*Dt
            if jj >= 1:
                indices.append([int(ll),int(jj-1)])
                temp= -(tao/(2*Dt))*((tao/Dt)-1)**2
                values.append(temp)
                
            if jj >= 0:
                indices.append([int(ll),int(jj)])
                temp= 1+((3*tao**3)/(2*Dt**3))-((5*tao**2)/(2*Dt**2))
                values.append(temp)
                
            if jj+1 <= steps-1:
                indices.append([int(ll),int(jj+1)])
                temp= ((tao)/(2*Dt))+((4*tao**2)/(2*Dt**2))-((3*tao**3)/(2*Dt**3))
                values.append(temp)
               
            if jj+2 <= steps-1:
                indices.append([int(ll),int(jj+2)])
                temp= ((tao**3)/(2*Dt**3))-((tao**2)/(2*Dt**2))
                values.append(temp)
                
            
        T1=tf.SparseTensor(indices, values, shape)  
        T2=tf.sparse_reorder(T1)
        T=tf.sparse_tensor_to_dense(T2)
        temp1 = tf.matmul(T,tf.reshape(w[0,:],[steps,1]))
        
        return tf.transpose(temp1)
    
    def init_tf_ops_weight(self):
        
        
        self.raw_weight =[]
        #tf weights of operators
        
            
        self.H0 = tf.Variable(tf.ones([self.sys_para.steps]), trainable=False)
        self.Hs_unpacked=[self.H0]


        if self.sys_para.u0 == []:
            initial_guess = 0
            index = 0
            self.raw_weight = []

            #initial_xy_stddev = (0.1/np.sqrt(self.sys_para.control_steps))
            initial_stddev = (0.1/np.sqrt(self.sys_para.steps))
            if self.sys_para.Dts != []:
                self.raw_weight = []
                if self.sys_para.ops_len - len(self.sys_para.Dts) > 0:
                    weights = tf.truncated_normal([self.sys_para.ops_len - len(self.sys_para.Dts) ,self.sys_para.steps],
                                                               mean= initial_guess ,dtype=tf.float32,
                        stddev=initial_stddev )

                    self.ops_weight_base = weights
                    current = weights[0,:]
                    for ii in range (self.sys_para.ops_len - len(self.sys_para.Dts)-1):
                        current = tf.concat(0,[current,weights[ii+1,:]])
                    self.current = tf.reshape(current,[1, (self.sys_para.ops_len - len(self.sys_para.Dts))*self.sys_para.steps])
                else:
                    initial_stddev = (0.1/np.sqrt(self.sys_para.ctrl_steps[0]))
                    weights = tf.truncated_normal([1 ,self.sys_para.ctrl_steps[0]],
                                                                   mean= initial_guess ,dtype=tf.float32,
                            stddev=initial_stddev )
                    index = 1
                    self.ops_weight_base = self.transfer_fn_general(weights,self.sys_para.ctrl_steps[0])
                    self.current = weights

                for ii in range (len(self.sys_para.Dts)-index):
                    initial_stddev = (0.1/np.sqrt(self.sys_para.ctrl_steps[ii+index]))
                    weight = tf.truncated_normal([1 ,self.sys_para.ctrl_steps[ii+index]],
                                                                   mean= initial_guess ,dtype=tf.float32,
                            stddev=initial_stddev )



                    self.current = tf.concat(1,[self.current,weight])


                self.raws = tf.Variable(self.current, dtype=tf.float32,name ="weights")

                self.raw_weight.append(self.raws[:,(self.sys_para.ops_len -len(self.sys_para.Dts))*self.sys_para.steps:(self.sys_para.ops_len -len(self.sys_para.Dts))*self.sys_para.steps+self.sys_para.ctrl_steps[0]])
                starting_index = (self.sys_para.ops_len -len(self.sys_para.Dts))*self.sys_para.steps + (index * self.sys_para.ctrl_steps[0])
                flag = False
                if index == 0:
                    flag = True


                for ii in range (len(self.sys_para.Dts)-index):
                    #R = tf.range(starting_index,starting_index + self.sys_para.ctrl_steps[ii+index],1)
                    #ws = tf.gather(self.raws,R)

                    ws = self.raws[:,starting_index:starting_index + self.sys_para.ctrl_steps[ii+index]]
                    self.ops_weight_base = tf.concat(0,[self.ops_weight_base,self.transfer_fn_general(ws,self.sys_para.ctrl_steps[ii+index])])
                    if flag:
                        flag = False
                    else:
                        self.raw_weight.append(ws)


                    starting_index = starting_index + self.sys_para.ctrl_steps[ii+index]





            else:

                self.ops_weight_base = tf.Variable(tf.truncated_normal([self.sys_para.ops_len,self.sys_para.steps],
                                                               mean= initial_guess ,dtype=tf.float32,
                        stddev=initial_stddev ),name="weights")
                self.raws = self.ops_weight_base


        else:
            self.op_weight = tf.constant(self.sys_para.u0[0],dtype=tf.float32)
            for ii in range (self.sys_para.ops_len-1):

                self.op_weight = tf.concat(0,[self.op_weight,self.sys_para.u0[ii+1]])
            self.op_weight = tf.reshape(self.op_weight, [self.sys_para.ops_len,self.sys_para.steps])
            self.ops_weight_base = tf.Variable(self.op_weight,dtype=tf.float32,name="weights")
            self.raws = self.ops_weight_base

        self.ops_weight = tf.tanh(self.ops_weight_base)
        for ii in range (self.sys_para.ops_len):
            self.Hs_unpacked.append(self.sys_para.ops_max_amp[ii]*self.ops_weight[ii,:])


        self.Hs = tf.pack(self.Hs_unpacked)
            
        #self.ops_weight = tf.tanh(self.ops_weight_base)
        
        
	
	
	print "Operators weight initialized."
                
    def init_tf_inter_states(self):
        #initialize intermediate states
        self.inter_states = []    
        for ii in range(self.sys_para.steps):
            self.inter_states.append(tf.zeros([2*self.sys_para.state_num,2*self.sys_para.state_num],
                                              dtype=tf.float32,name="inter_state_"+str(ii)))
        print "Intermediate states initialized."
            
    def get_inter_state_op(self,layer):
        # build opertor for intermediate state propagation
        # This function determines the nature of propagation
        matrix_list = self.H0_flat
        for ii in range(self.sys_para.ops_len):
            matrix_list = matrix_list + self.flat_ops[ii]
        matrix_list = matrix_list + self.I_flat
        
        propagator = self.matrix_exp_module.matrix_exp(self.Hs[:,layer],size=2*self.sys_para.state_num, input_num = self.sys_para.ops_len+1,
                                      exp_num = self.sys_para.exp_terms, div = self.sys_para.div
                                      ,matrix=matrix_list)
        
        
        return propagator    
        
    def init_tf_propagator(self):
        # build propagator for all the intermediate states
        
        #first intermediate state
        self.inter_states[0] = tf.matmul(self.get_inter_state_op(0),self.tf_initial_state)
        #subsequent operation layers and intermediate states
        for ii in np.arange(1,self.sys_para.steps):
            self.inter_states[ii] = tf.matmul(self.get_inter_state_op(ii),self.inter_states[ii-1])
            
        #apply global phase operator to final state
        self.final_state = self.inter_states[self.sys_para.steps-1]
        
        self.unitary_scale = (0.5/self.sys_para.state_num)*tf.reduce_sum(tf.matmul(tf.transpose(self.final_state),self.final_state))
        
        print "Propagator initialized."
        
    def init_tf_inter_vectors(self):
        self.inter_vecs=[]
        
        for tf_initial_vector in self.tf_initial_vectors:
        
            inter_vec = tf.reshape(tf_initial_vector,[2*self.sys_para.state_num,1])
            for ii in np.arange(0,self.sys_para.steps):
                inter_vec_temp = tf.matmul(self.inter_states[ii],tf.reshape(tf_initial_vector,[2*self.sys_para.state_num,1]))
                inter_vec = tf.concat(1,[inter_vec,inter_vec_temp])
                
            self.inter_vecs.append(inter_vec)
            
        print "Vectors initialized."
        
        
    def init_training_loss(self):

        inner_product = tf.matmul(tf.transpose(self.tf_target_state),self.final_state)
        inner_product_trace_real = tf.reduce_sum(tf.pack([inner_product[ii,ii] for ii in self.sys_para.states_concerned_list]))\
        /float(len(self.sys_para.states_concerned_list))
        inner_product_trace_imag = tf.reduce_sum(tf.pack([inner_product[self.sys_para.state_num+ii,ii] for ii in self.sys_para.states_concerned_list]))\
        /float(len(self.sys_para.states_concerned_list))
        
        inner_product_trace_mag_squared = tf.square(inner_product_trace_real) + tf.square(inner_product_trace_imag)
        
        self.loss = tf.abs(1 - inner_product_trace_mag_squared)
    
    
        # Regulizer
        self.reg_loss = self.loss
        self.reg_alpha_coeff = tf.placeholder(tf.float32,shape=[])
        reg_alpha = self.reg_alpha_coeff/float(self.sys_para.steps)
        self.reg_loss = self.reg_loss + reg_alpha * tf.nn.l2_loss(tf.mul(self.tf_one_minus_gaussian_evelop,self.ops_weight))
        
        # Constrain Z to have no dc value
        self.z_reg_alpha_coeff = tf.placeholder(tf.float32,shape=[])
        z_reg_alpha = self.z_reg_alpha_coeff/float(self.sys_para.steps)
        #self.reg_loss = self.reg_loss + z_reg_alpha*tf.square(tf.reduce_sum(self.ops_weight[2,:]))
        
        # Limiting the dwdt of control pulse
        self.dwdt_reg_alpha_coeff = tf.placeholder(tf.float32,shape=[])
        dwdt_reg_alpha = self.dwdt_reg_alpha_coeff/float(self.sys_para.steps)
        self.reg_loss = self.reg_loss + dwdt_reg_alpha*tf.nn.l2_loss((self.ops_weight[:,1:]-self.ops_weight[:,:self.sys_para.steps-1])/self.sys_para.dt)
        
        # Limiting the d2wdt2 of control pulse
        self.d2wdt2_reg_alpha_coeff = tf.placeholder(tf.float32,shape=[])
        d2wdt2_reg_alpha = self.d2wdt2_reg_alpha_coeff/float(self.sys_para.steps)
        self.reg_loss = self.reg_loss + d2wdt2_reg_alpha*tf.nn.l2_loss((self.ops_weight[:,2:] -\
                        2*self.ops_weight[:,1:self.sys_para.steps-1] +self.ops_weight[:,:self.sys_para.steps-2])/(self.sys_para.dt**2))
        
        # Limiting the access to forbidden states
        self.inter_reg_alpha_coeff = tf.placeholder(tf.float32,shape=[])
        inter_reg_alpha = self.inter_reg_alpha_coeff/float(self.sys_para.steps)
        
        for inter_vec in self.inter_vecs:
            for state in self.sys_para.states_forbidden_list:
                forbidden_state_pop = tf.square(0.5*(inter_vec[state,:] +\
                                                     inter_vec[self.sys_para.state_num + state,:])) +\
                                    tf.square(0.5*(inter_vec[state,:] -\
                                                     inter_vec[self.sys_para.state_num + state,:]))
                self.reg_loss = self.reg_loss + inter_reg_alpha * tf.nn.l2_loss(forbidden_state_pop)
            
        print "Training loss initialized."
            
    def init_optimizer(self):
        # Optimizer. Takes a variable learning rate.
        self.learning_rate = tf.placeholder(tf.float32,shape=[])
        self.opt = tf.train.AdamOptimizer(learning_rate = self.learning_rate)
        
        #Here we extract the gradients of the xy and z pulses
        self.grad = self.opt.compute_gradients(self.reg_loss)
        if self.sys_para.Dts == [] :
            self.grad_pack = tf.pack([g for g, _ in self.grad])
        
        else:
            self.grad_pack,_ = self.grad[0]
            for ii in range (len(self.grad)-1):
                a,_ = self.grad[ii+1]
                self.grad_pack = tf.concat(1,[self.grad_pack,a])
        
        self.grads =[tf.nn.l2_loss(g) for g, _ in self.grad]
        self.grad_squared = tf.reduce_sum(tf.pack(self.grads))
        self.optimizer = self.opt.apply_gradients(self.grad)
        
        print "Optimizer initialized."
    
    def init_utilities(self):
        # Add ops to save and restore all the variables.
        self.saver = tf.train.Saver()
        
        print "Utilities initialized."
        
      
            
    def build_graph(self):
        graph = tf.Graph()
        with graph.as_default():
            
            print "Building graph:"
            
            self.init_variables()
            self.init_tf_vectors()
            self.init_tf_states()
            self.init_tf_ops()
            self.init_tf_ops_weight()
            self.init_tf_inter_states()
            self.init_tf_propagator()
            self.init_tf_inter_vectors()
            self.init_training_loss()
            self.init_optimizer()
            self.init_utilities()
            
            print "Graph built!"

        return graph
