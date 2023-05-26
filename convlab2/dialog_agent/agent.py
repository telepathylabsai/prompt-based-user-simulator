"""Dialog agent interface and classes."""
from abc import ABC, abstractmethod
from convlab2.nlu import NLU
from convlab2.dst import DST
from convlab2.policy import Policy
from convlab2.nlg import NLG
from copy import deepcopy


class Agent(ABC):
    """Interface for dialog agent classes."""
    @abstractmethod
    def __init__(self, name: str):
        self.name = name

    @abstractmethod
    def response(self, observation):
        """Generate agent response given user input.

        The data type of input and response can be either str or list of tuples, condition on the form of agent.

        Example:
            If the agent is a pipeline agent with NLU, DST and Policy, then type(input) == str and
            type(response) == list of tuples.
        Args:
            observation (str or list of tuples):
                The input to the agent.
        Returns:
            response (str or list of tuples):
                The response generated by the agent.
        """
        pass

    @abstractmethod
    def init_session(self, **kwargs):
        """Reset the class variables to prepare for a new session."""
        pass


class PipelineAgent(Agent):
    """Pipeline dialog agent base class, including NLU, DST, Policy and NLG.

    The combination modes of pipeline agent modules are flexible. The only thing you have to make sure is that
    the API of agents are matched.

    Example:
        If agent A is (nlu, tracker, policy), then the agent B should be like (tracker, policy, nlg) to ensure API
        matching.
    The valid module combinations are as follows:
           =====   =====    ======  ===     ==      ===
            NLU     DST     Policy  NLG     In      Out
           =====   =====    ======  ===     ==      ===
            \+      \+        \+    \+      nl      nl
             o      \+        \+    \+      da      nl
             o      \+        \+     o      da      da
            \+      \+        \+     o      nl      da
             o       o        \+     o      da      da
           =====   =====    ======  ===     ==      ===
    """

    def __init__(self, nlu: NLU, dst: DST, policy: Policy, nlg: NLG, name: str):
        """The constructor of PipelineAgent class.

        Here are some special combination cases:

            1. If you use word-level DST (such as Neural Belief Tracker), you should set the nlu_model paramater \
             to None. The agent will combine the modules automitically.

            2. If you want to aggregate DST and Policy as a single module, set tracker to None.

        Args:
            nlu (NLU):
                The natural langauge understanding module of agent.

            dst (DST):
                The dialog state tracker of agent.

            policy (Policy):
                The dialog policy module of agent.

            nlg (NLG):
                The natural langauge generator module of agent.
        """
        super(PipelineAgent, self).__init__(name=name)
        assert self.name in ['user', 'sys']
        self.opponent_name = 'user' if self.name is 'sys' else 'sys'
        self.nlu = nlu
        self.dst = dst
        self.policy = policy
        self.nlg = nlg
        self.init_session()
        self.history = []

    def state_replace(self, agent_state):
        """
        this interface is reserved to replace all interal states of agent
        the code snippet example below is for the scenario when the agent state only depends on self.history and self.dst.state
        """
        self.history = deepcopy(agent_state['history'])
        self.dst.state = deepcopy(agent_state['dst_state'])

    def state_return(self):
        """
        this interface is reserved to return all interal states of agent
        the code snippet example below is for the scenario when the agent state only depends on self.history and self.dst.state
        """
        agent_state = {}
        agent_state['history'] = deepcopy(self.history)
        agent_state['dst_state'] = deepcopy(self.dst.state)

        return agent_state

    def response(self, observation):
        """Generate agent response using the agent modules."""
        # Note: If you modify the logic of this function, please ensure that it is consistent with deploy.server.ServerCtrl._turn()
        if self.dst is not None:
            self.dst.state['history'].append([self.opponent_name, observation]) # [['sys', sys_utt], ['user', user_utt],...]
        self.history.append([self.opponent_name, observation])
        # get dialog act
        if self.nlu is not None:
            self.input_action = self.nlu.predict(observation, context=[x[1] for x in self.history[:-1]])
        else:
            self.input_action = observation
        self.input_action = deepcopy(
            self.input_action)  # get rid of reference problem
        # get state
        if self.dst is not None:
            if self.name is 'sys':
                self.dst.state['user_action'] = self.input_action
            else:
                self.dst.state['system_action'] = self.input_action
            state = self.dst.update(self.input_action)
        else:
            state = self.input_action
        state = deepcopy(state)  # get rid of reference problem
        # get action
        self.output_action = deepcopy(
            self.policy.predict(state))  # get rid of reference problem
        # get model response
        if self.nlg is not None:
            model_response = self.nlg.generate(self.output_action)
        else:
            model_response = self.output_action
        # print(model_response)
        if self.dst is not None:
            self.dst.state['history'].append([self.name, model_response])
            if self.name == 'sys':
                self.dst.state['system_action'] = self.output_action
            else:
                self.dst.state['user_action'] = self.output_action
        self.history.append([self.name, model_response])
        return model_response

    def is_terminated(self):
        if hasattr(self.policy, 'is_terminated'):
            return self.policy.is_terminated()
        return None

    def get_reward(self):
        if hasattr(self.policy, 'get_reward'):
            return self.policy.get_reward()
        return None

    def init_session(self, **kwargs):
        """Init the attributes of DST and Policy module."""
        if self.nlu is not None:
            self.nlu.init_session()
        if self.dst is not None:
            self.dst.init_session()
            if self.name == 'sys':
                self.dst.state['history'].append([self.name, 'null'])
        if self.policy is not None:
            self.policy.init_session(**kwargs)
        if self.nlg is not None:
            self.nlg.init_session()
        self.history = []

    def get_in_da(self):
        return self.input_action

    def get_out_da(self):
        return self.output_action
