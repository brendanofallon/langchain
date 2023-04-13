from typing import Any, Dict, List, Optional
import json
from pathlib import Path

from pydantic import root_validator

from langchain.memory.chat_memory import BaseChatMemory, BaseMemory, ChatMessageHistory
from langchain.memory.utils import get_prompt_input_key
from langchain.schema import get_buffer_string, HumanMessage, AIMessage, SystemMessage, ChatMessage


class ConversationBufferMemory(BaseChatMemory):
    """Buffer for storing conversation memory."""

    human_prefix: str = "Human"
    ai_prefix: str = "AI"
    memory_key: str = "history"  #: :meta private:

    @property
    def buffer(self) -> Any:
        """String buffer of memory."""
        if self.return_messages:
            return self.chat_memory.messages
        else:
            return get_buffer_string(
                self.chat_memory.messages,
                human_prefix=self.human_prefix,
                ai_prefix=self.ai_prefix,
            )

    @property
    def memory_variables(self) -> List[str]:
        """Will always return list of memory variables.

        :meta private:
        """
        return [self.memory_key]

    def load_memory_variables(self, inputs: Dict[str, Any]) -> Dict[str, Any]:
        """Return history buffer."""
        return {self.memory_key: self.buffer}


class ConversationStringBufferMemory(BaseMemory):
    """Buffer for storing conversation memory."""

    human_prefix: str = "Human"
    ai_prefix: str = "AI"
    """Prefix to use for AI generated responses."""
    buffer: str = ""
    output_key: Optional[str] = None
    input_key: Optional[str] = None
    memory_key: str = "history"  #: :meta private:

    @root_validator()
    def validate_chains(cls, values: Dict) -> Dict:
        """Validate that return messages is not True."""
        if values.get("return_messages", False):
            raise ValueError(
                "return_messages must be False for ConversationStringBufferMemory"
            )
        return values

    @property
    def memory_variables(self) -> List[str]:
        """Will always return list of memory variables.
        :meta private:
        """
        return [self.memory_key]

    def load_memory_variables(self, inputs: Dict[str, Any]) -> Dict[str, str]:
        """Return history buffer."""
        return {self.memory_key: self.buffer}

    def save_context(self, inputs: Dict[str, Any], outputs: Dict[str, str]) -> None:
        """Save context from this conversation to buffer."""
        if self.input_key is None:
            prompt_input_key = get_prompt_input_key(inputs, self.memory_variables)
        else:
            prompt_input_key = self.input_key
        if self.output_key is None:
            if len(outputs) != 1:
                raise ValueError(f"One output key expected, got {outputs.keys()}")
            output_key = list(outputs.keys())[0]
        else:
            output_key = self.output_key
        human = f"{self.human_prefix}: " + inputs[prompt_input_key]
        ai = f"{self.ai_prefix}: " + outputs[output_key]
        self.buffer += "\n" + "\n".join([human, ai])

    def clear(self) -> None:
        """Clear memory contents."""
        self.buffer = ""



class SerializingConversationMemory(BaseChatMemory):
    """Buffer for storing conversation memory."""

    human_prefix: str = "Human"
    ai_prefix: str = "AI"
    memory_key: str = "history"  #: :meta private:
    chat_log_file: str = "chat_log.log"
    context_msgs: int = 4

    @property
    def buffer(self) -> Any:            
        # Blow away existing memory? - can something else add memories we're not aware of?
        self.chat_memory = self._load_messages()
        self.chat_memory.messages = self.chat_memory.messages[-self.context_msgs:]

        if self.return_messages:
            return self.chat_memory.messages
        else:
            return get_buffer_string(
                self.chat_memory.messages,
                human_prefix=self.human_prefix,
                ai_prefix=self.ai_prefix,
            )
    def _load_messages(self):
        chatlog = Path(self.chat_log_file)
        if not chatlog.exists():
            chatlog.touch()
            return ChatMessageHistory(messages=[])

        messages = []
        with open(chatlog, "r") as fh:
            content = fh.read().strip()
            if not content:
                return ChatMessageHistory(messages=[])
            for line in content.split("\n"):
                entry = json.loads(line)
                if entry['type'] == "human":
                    msg = HumanMessage(content=entry['content'], additional_kwargs=entry['kwargs'])
                elif entry['type'] == "ai":
                    msg = AIMessage(content=entry['content'], additional_kwargs=entry['kwargs'])
                elif entry['type'] == "system":
                    msg = SystemMessage(content=entry['content'], additional_kwargs=entry['kwargs'])
                elif entry['type'] == "chat":
                    msg = ChatMessage(content=entry['content'], additional_kwargs=entry['kwargs'])

                messages.append(msg)
        return ChatMessageHistory(messages=messages)

    def _write_messages(self):
        with open(self.chat_log_file, "a") as fh:
            for msg in self.chat_memory.messages:
                m = {"type": msg.type, "content": msg.content, "kwargs": msg.additional_kwargs}
                fh.write(json.dumps(m) + "\n")

    def save_context(self, inputs: Dict[str, Any], outputs: Dict[str, str]) -> None:
        """Save context from this conversation to buffer."""
        if self.input_key is None:
            prompt_input_key = get_prompt_input_key(inputs, self.memory_variables)
        else:
            prompt_input_key = self.input_key
        if self.output_key is None:
            if len(outputs) != 1:
                raise ValueError(f"One output key expected, got {outputs.keys()}")
            output_key = list(outputs.keys())[0]
        else:
            output_key = self.output_key
        self.chat_memory.add_user_message(inputs[prompt_input_key])
        self.chat_memory.add_ai_message(outputs[output_key])
        self._write_messages()

    def add_score(self, score):
        self.chat_memory = self._load_messages()
        self.chat_memory.messages[-1].additional_kwargs['score'] = score
        self._write_messages()

    @property
    def memory_variables(self) -> List[str]:
        """Will always return list of memory variables.

        :meta private:
        """
        return [self.memory_key]

    def load_memory_variables(self, inputs: Dict[str, Any]) -> Dict[str, Any]:
        """Return history buffer."""
        return {self.memory_key: self.buffer}
