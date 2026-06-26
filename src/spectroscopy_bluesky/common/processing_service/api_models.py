from pydantic import BaseModel


class ProcessorOutput(BaseModel):
    output_path: str
    function_name: str
    data_names: list[str]

class ProcessorSetup(BaseModel):
    input_file: str
    output_file: str
    no_new_data_timeout: float = 5.0
    process_loop_sleep_secs: float = 1.0
    processor_outputs: list[ProcessorOutput]
