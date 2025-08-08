from __future__ import annotations

from typing import List, Tuple
from functools import wraps
import re
from dataclasses import dataclass

@dataclass
class GTokens:
    """Data structure to hold G-code tokens"""
    tokens: List[List[str]]
    original_line: str

modal_groups = {
    'gcode': {
        'motion': ['G0', 'G1', 'G2', 'G3', 'G33', 'G38.*', 'G73', 'G76', 'G80', 'G81', 'G82', 'G83', 'G84', 'G85', 'G86', 'G87', 'G88', 'G89'],
        'plane_selection': ['G17', 'G18', 'G19', 'G17.1', 'G17.2', 'G17.3'],
        'distance_mode': ['G90', 'G91'],
        'ijk_distance_mode': ['G90.1', 'G91.1'],
        'feedrate_mode': ['G93', 'G94'],
        'units': ['G20', 'G21'],
        'cutter_radius_compensation': ['G40', 'G41', 'G42', 'G41.1', 'G42.1'],
        'tool_length_offset': ['G43', 'G43.1', 'G49'],
        'return_mode' :['G98', 'G99'],
        'coordinate_system': ['G54', 'G55', 'G56', 'G57', 'G58', 'G59', 'G59.1', 'G59.2', 'G59.3'],
        'path_control': ['G61', 'G61.1', 'G64'],
        'spindle_speed': ['G96', 'G97'],
        'lathe_diameter': ['G7', 'G8'],
    },
    'mcode': {
        'stopping': ['M0', 'M1', 'M2', 'M30', 'M60'],
        'spindle_control': ['M3', 'M4', 'M5'],
        'coolant_control': ['M7', 'M8', 'M9'],
        'feed_speed_override': ['M48', 'M49'],
        'tool_change': ['M6'],
    },
    'other': {
        'nonmodal': ['G4', 'G10', 'G28', 'G30', 'G92', 'G92.1', 'G92.2', 'G92.3'],
    }
}

def split_code(code: str):
    """Split a G-code into its components"""
    code_type = code[0].lower()

    if code_type == '%':
        return '%', code[1:]

    code_num = int(code[1:].split('.')[0])

    return code_type, code_num

# Create regex and hashmap for verification and fast lookup
code_lookup = {}
for code_type in modal_groups:
    for modal_group in modal_groups[code_type]:
        for i, code in enumerate(modal_groups[code_type][modal_group]):
            code_letter, major_num = split_code(code)

            # Create regex
            regex = code
            regex = regex.replace('.', '\\.')
            regex = regex.replace('*', '\\d+')
            regex = regex[0] + '[0]*' + code[1:]
            regex = re.compile(regex)

            # Save in hashmap
            code_lookup.setdefault((code_letter, major_num), []).append((code_type, modal_group, regex))

def get_modal_group(token: str) -> Tuple[str, str, str]:
    """Get the modal group and type for a G-code token"""
    code_letter, major_num = split_code(token)

    if code_letter == '%':
        return 'custom', 'custom'

    possible_matches = code_lookup.get((code_letter, major_num), [])
    for code_type, modal_group, regex in possible_matches:
        if regex.fullmatch(token):
            return code_type, modal_group

    return None, None

class GCodeProcessor:
    def __init__(self):
        self.tokens: List[List[str]] = []
        self.token_transformers: List[TokenTransformer] = []

    def reset(self):
        """Reset the tokenizer state"""
        self.tokens.clear()
        for transformer in self.token_transformers:
            transformer.reset()

    def process_line(self, line: str):
        """Add a line of G-code and return the tokens"""
        tokens = self.tokenize(line)
        metadata = [dict() for _ in range(len(tokens))]

        done = False
        while not done:
            done = True

            tokens_new = []
            while tokens:
                token = tokens.pop(0)
                token_metadata = metadata.pop(0)

                token_transformed = False
                for transformer in self.token_transformers:
                    if transformer.can_transform(token, token_metadata):
                        transformed = transformer.process(token, token_metadata)
                        for transformed_token in reversed(transformed):
                            tokens.insert(0, transformed_token)
                            metadata.insert(0, token_metadata.copy())
                        token_transformed = True
                        break

                if not token_transformed:
                    tokens_new.append(token)
                    for transformer in self.token_transformers:
                        transformer.observe(token, token_metadata)
            
            self.tokens.append(tokens_new)
    
    def token_processor(self):
        def decorator(cls):
            instance = cls()
            instance.set_transformer(self)
            self.token_transformers.append(instance)
            return cls
        return decorator

    def tokens_to_lines(self, tokens: List[str]) -> List[str]:
        lines = []
        modal_groups = []
        line_tokens = []
        for token in tokens:
            code_type, modal_group = get_modal_group(token)

            if modal_group and modal_group == 'custom':
                if line_tokens:
                    lines.append(' '.join(line_tokens))
                    line_tokens.clear()
                    modal_groups.clear()
                lines.append(token)
                continue

            if not modal_group or modal_group == 'nonmodal':
                line_tokens.append(token)
                continue

            
            if (code_type, modal_group) in modal_groups:
                lines.append(' '.join(line_tokens))
                line_tokens = [token]
                modal_groups = [(code_type, modal_group)]
            else:           
                line_tokens.append(token)
                modal_groups.append((code_type, modal_group))
        
        if line_tokens:
            lines.append(' '.join(line_tokens))

        return lines

    def add_token_transformer(self, token_processor):
        self.token_processors.append(token_processor)
    
    def remove_token_processor(self, token_processor):
        if token_processor in self.token_processors:
            self.token_processors.remove(token_processor)

    def tokenize(self, line: str) -> None:
        """Create tokens from a G-code line"""
        line = re.sub(r'\s*', '', line)
        tokens = re.findall(r'\D\d+', line)
        return tokens

    def process_tokens(self, tokens: List[str]):
        return tokens

    def get_lines(self) -> List[str]:
        """Get the processed G-code lines from the tokens"""
        lines = []
        for token_list in self.tokens:
            lines.extend(self.tokens_to_lines(token_list))
        
        return lines

class TokenTransformer:
    """Base class for transforming G-code tokens"""
    def __init__(self):
        self.tokenizer: GCodeProcessor = None

    def set_transformer(self, tokenizer: GCodeProcessor):
        """Set the tokenizer for this transformer"""
        self.tokenizer = tokenizer

    def reset(self):
        """Reset the transformer state"""
        pass

    def can_transform(self, token: str, metadata) -> bool:
        """Check if this transformer can process the given token"""
        return False

    def process(self, token, metadata) -> List[str]:
        """Process the token and return a transformed version. If no changes, return None."""

    def observe(self, token, metadata):
        pass

_gcode_processor: GCodeProcessor = None

def get_gcode_processor() -> GCodeProcessor:
    """Get the global GCodeProcessor instance"""
    global _gcode_processor
    if _gcode_processor is None:
        raise RuntimeError("GCodeProcessor is not initialized. Call set_gcode_processor() first.")
    return _gcode_processor

def set_gcode_processor(processor: GCodeProcessor):
    """Set the global GCodeProcessor instance"""
    global _gcode_processor
    if _gcode_processor is not None:
        raise RuntimeError("GCodeProcessor is already set")
    _gcode_processor = processor

gcode_processor = GCodeProcessor()
set_gcode_processor(gcode_processor)

@gcode_processor.token_processor()
class M0Transformer(TokenTransformer):
    """Transformer for M0 commands"""
    def can_transform(self, token: str, _metadata) -> bool:
        if 'm0_transformer' in _metadata and _metadata['m0_transformer']:
            return False
        
        if token.startswith('M0'):
            _metadata['m0_transformer'] = True
            return True
    
    def process(self, token: str, metadata) -> List[str]:
        """Transform M0 command to a different format"""
        return ['%wait_for_idle', 'M0']

if __name__ == "__main__":
    lines = """G1 X10 Y20 Z30 G1 X20 M3 T1
    G2 X15 Y25 Z35 M0 M5 T2
    G1 X20 Y30 Z40 M4 T3""".strip().split('\n')

    code_type, modal_group = get_modal_group('G1')
    
    gcode_processor = get_gcode_processor()

    gcode_processor.reset()
    for line in lines:
        gcode_processor.process_line(line)
    new_lines = gcode_processor.get_lines()

    print('\n'.join(new_lines))