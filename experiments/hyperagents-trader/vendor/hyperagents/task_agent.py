from agent.base_agent import AgentSystem
from agent.llm_withtools import chat_with_agent
from utils.common import extract_jsons

class TaskAgent(AgentSystem):
    def forward(self, inputs):
        """
        An agent that solves a given task.

        Args:
            inputs (dict): A dictionary with input data for the task.

        Returns:
            tuple:
                - prediction (str): The prediction made by the agent.
                - new_msg_history (list): A list of messages representing the message history of the interaction.
        """
        domain = inputs['domain']

        # alpaca_trading needs a structured multi-field decision (orders + a
        # rationale), not the single "response" string every other domain
        # here uses -- everything else below is unchanged from upstream.
        if domain == "alpaca_trading":
            instruction = f"""You are a trading agent deciding what to do for one trading day.

Task input:
```
{inputs}
```

`positions` are shares currently held; `market_data` has each symbol's last
price and moving averages; `risk_limits` are hard caps enforced regardless of
what you propose (no need to self-limit beyond them). Respond in JSON:
<json>
{{
    "orders": [{{"symbol": "...", "side": "buy or sell", "qty": 0}}],
    "rationale": "..."
}}
</json>
Return "orders": [] to hold with no trades."""
            new_msg_history = chat_with_agent(instruction, model=self.model, msg_history=[], logging=self.log)
            prediction = {"orders": [], "rationale": "no valid response"}
            try:
                extracted_jsons = extract_jsons(new_msg_history[-1]['text'])
                if extracted_jsons is not None and "orders" in extracted_jsons[-1]:
                    prediction = {
                        "orders": extracted_jsons[-1].get("orders", []),
                        "rationale": extracted_jsons[-1].get("rationale", ""),
                    }
            except Exception as e:
                self.log(f"Error extracting prediction: {e}")
            return prediction, new_msg_history

        instruction = f"""You are an agent.

Task input:
```
{inputs}
```

Respond in JSON format with the following schema:
<json>
{{
    "response": ...
}}
</json>"""
        new_msg_history = chat_with_agent(instruction, model=self.model, msg_history=[], logging=self.log)

        # Extract the response
        prediction = "None"
        try:
            extracted_jsons = extract_jsons(new_msg_history[-1]['text'])
            if extracted_jsons is not None and "response" in extracted_jsons[-1]:
                prediction = extracted_jsons[-1]['response']
        except Exception as e:
            self.log(f"Error extracting prediction: {e}")
            prediction = "None"

        return prediction, new_msg_history
