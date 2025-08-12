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
    
    try:
        code_num = int(code[1:].split('.')[0])
    except:
        code_num = code[1:]

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

class Token:
    def __init__(self, token: str, metadata=None):
        self.token = token
        self.metadata = metadata if metadata is not None else {}

class GCodeProcessor:
    def __init__(self):
        self.tokens: List[List[Token]] = []
        self.token_transformers: List[TokenTransformer] = []

    def reset(self):
        """Reset the tokenizer state"""
        self.tokens.clear()
        for transformer in self.token_transformers:
            transformer.reset()

    def extract_comments(self, line: str):
        if line.startswith(';'):
            return "", line[1:].strip()
        
        comments = re.findall(r'\((.*?)\)', line)
        line = re.sub(r'\(.+\)', '', line)  # Remove comments

        return line.strip(), comments

    def strip_whitespace(self, line: str) -> str:
        """Strip whitespace from a G-code line"""
        return re.sub(r'\s+', ' ', line).strip()

    def process_lines(self, lines: str):
        """Add a line of G-code and return the tokens"""

        comments_all: List[str] = []
        tokens_all: List[List[Token]]  = []
        for line in lines:
            line = line.strip()
            line, comments = self.extract_comments(line)
            tokens = self.tokenize(line)

            if not tokens:
                continue

            for token in tokens:
                token.metadata = {'original_line': line, 'comments': comments, 'visited': set()}

            comments_all.append(comments)
            tokens_all.append(tokens)
        
        self.current_line = 0
        self.current_token = 0

        self.tokens = tokens_all

        while self.current_line < len(self.tokens):
            tokens = tokens_all[self.current_line]

            while self.current_token < len(tokens):
                token = tokens[self.current_token]

                token_transformed = False
                for transformer in self.token_transformers:
                    if transformer in token.metadata['visited']:
                        continue

                    if num_tokens := transformer.can_transform():
                        transform_tokens = list(reversed([tokens.pop() for _ in range(num_tokens)]))
                        transformed = transformer.process(transform_tokens)

                        for token in transformed:
                            token.metadata.setdefault('visited', set()).add(transformer)
                        
                        for transformed_token in reversed(transformed):
                            tokens.insert(self.current_token, transformed_token)
                        token_transformed = True
                        break

                if not token_transformed:
                    for transformer in self.token_transformers:
                        transformer.observe(token)
                    self.current_token += 1
            self.current_token = 0
            self.current_line += 1

    def seek(self, offset: int = 0):
        """Find the line/position by an offset from the current position"""  
        pos = self.current_token
        line = self.current_line

        while offset < 0:
            if line < 0:
                return None, None

            if pos >= -offset:
                pos += offset
                offset = 0
            else:
                offset += pos
                line -= 1
                pos = len(self.tokens[line]) - 1

        while offset > 0:
            if line >= len(self.tokens):
                return None, None

            num_tokens = len(self.tokens[line])
            if pos + offset >= num_tokens:
                offset -= (num_tokens - pos)
                line += 1
                pos = 0
            else:
                pos += offset
                offset = 0

        return line, pos
    
    def token_iterator(self, offset: int = 0, traverse_lines: bool = True, reverse=False):
        """Generator to iterate over tokens"""
        line, pos = self.seek(offset)

        if line is None or pos is None:
            return

        while 0 <= line < len(self.tokens):
            yield self.tokens[line][pos]

            if reverse:
                pos -= 1
                if pos < 0:
                    if traverse_lines:
                        line -= 1
                        pos = len(self.tokens[line]) - 1
                        continue
                    else:
                        break
            else:
                pos += 1
                if pos >= len(self.tokens[line]):
                    if traverse_lines:
                        line += 1
                        pos = 0
                        continue
                    else:
                        break
            

    def peek(self, offset: int = 0, count=1) -> str:
        """Peek at the next token without consuming it"""
        original_count = count
        
        if count <= 0:
            return None
        
        result = []
        it = self.token_iterator(offset, traverse_lines=False)
        try:
            for _ in range(count):
                token = next(it)
                result.append(token)
        except StopIteration:
            pass

        if result:
            if original_count == 1:
                return result[0]
            return result
        else:
            return None

    def token_processor(self):
        def decorator(cls):
            instance = cls()
            instance.set_transformer(self)
            self.token_transformers.append(instance)
            return cls
        return decorator

    def tokens_to_lines(self, tokens: List[Token]) -> List[str]:
        lines = []
        modal_groups = []
        line_tokens = []
        for token in tokens:
            token = token.token
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

    def tokenize(self, line: str) -> List[Token]:
        """Create tokens from a G-code line"""
        tokens = re.findall(r'(\D(([-0123456789.]+)|(\[.+?\])))', line)
        tokens = [Token(token[0]) for token in tokens if token[0]]  # Flatten the tuple and remove empty strings
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
        self.processor: GCodeProcessor = None

    def set_transformer(self, processor: GCodeProcessor):
        """Set the tokenizer for this transformer"""
        self.processor = processor

    def reset(self):
        """Reset the transformer state"""
        pass

    def can_transform(self) -> int:
        """Check if this transformer can process starting at the current position"""
        return False

    def process(self, tokens: List[Token]) -> List[str]:
        """Process the token and return a transformed version. If no changes, return None."""

    def observe(self, token: Token):
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
    def can_transform(self) -> bool:
        token = self.processor.peek(0)
        if token.token.startswith('M0'):
            if self.processor.peek(1) != '%wait_for_idle':
                return 1
        return 0
    
    def process(self, tokens: List[Token]) -> List[str]:
        """Transform M0 command to a different format"""
        return [Token('%wait_for_idle')] + tokens + [Token('%wait_for_last_command')]
    
@gcode_processor.token_processor()
class ProbeAndWait(TokenTransformer):
    """Pauses sending commands until probe command is complete"""
    def can_transform(self) -> int:
        token = self.processor.peek(0).token
        if token.startswith('G38'):
            # if 'probe_and_wait' in metadata and metadata['probe_and_wait']:
            #     return False
            
            it = self.processor.token_iterator(1, traverse_lines=False)
            num_tokens = 1
            try:
                while True:
                    next_token = next(it).token
                    first_char = next_token[0].lower()

                    if first_char == 'g' or first_char == 'm':
                        return num_tokens
                    elif first_char == '%':
                        if next_token == '%wait_for_last_command':
                            return 0
                    else:
                        num_tokens += 1
            except StopIteration:
                return num_tokens
        return 0
    
    def process(self, tokens: List[str]) -> Tuple[int, List[str]]:
        """Transform M0 command to a different format"""
        tokens = tokens.copy()

        # it = self.processor.token_iterator(1, traverse_lines=False)
        # try:
        #     while True:
        #         next_token = next(it)
        #         first_char = next_token.token[0].lower()

        #         if first_char == 'g' or first_char == 'm':
        #             break
                
        #         tokens.append(next_token)
        # except StopIteration:
        #     pass

        tokens.append(Token('%wait_for_last_command'))

        return tokens

if __name__ == "__main__":
    lines = """G1 X10 Y20 Z30 G1 X20 M3 T1
    G2 X15 Y25 Z35 M0 M5 T2
    G1 X20 Y30 Z40 M4 T3
    G38.2 Z-10 F50
    G4 P1
    G43.1 Z[posz]""".strip().split('\n')

    code_type, modal_group = get_modal_group('G1')
    
    gcode_processor = get_gcode_processor()

    gcode_processor.reset()
    # for line in lines:
    #     gcode_processor.process_line(line)
    gcode_processor.process_lines(lines)
    new_lines = gcode_processor.get_lines()

    print('\n'.join(new_lines))
