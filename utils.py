"""
Módulo de procesamiento de PDF para documentación técnica de Volaris.
Contiene toda la lógica de limpieza y preparación de documentos.
"""

import os
import re
import tempfile
from typing import List, Tuple, Optional, Dict, Any
import PyPDF2
from PyPDF2 import PdfReader, PdfWriter
import pdfplumber
from dataclasses import dataclass
from enum import Enum

class TaskType(Enum):
    TASK_CARD = "TASK CARD"
    ENGINEERING_ORDER = "ENGINEERING ORDER"
    DAILY_CHECK = "DAILY CHECK"
    WEEKLY_CHECK = "WEEKLY CHECK"
    OTHER = "OTHER"

@dataclass
class TaskSection:
    """Representa una sección de tarea identificada en el PDF."""
    start_page: int
    end_page: int
    task_type: TaskType
    task_name: str
    work_order: Optional[str] = None

class PDFProcessor:
    """Procesador principal de documentos PDF."""
    
    def __init__(self, add_blank_pages: bool = True, remove_metadata: bool = True):
        """
        Inicializa el procesador.
        
        Args:
            add_blank_pages: Si se deben añadir páginas en blanco para doble cara
            remove_metadata: Si se deben eliminar páginas de metadatos
        """
        self.add_blank_pages = add_blank_pages
        self.remove_metadata = remove_metadata
        self.temp_files = []  # Para rastrear archivos temporales
        
    def cleanup_temp_files(self):
        """Limpia todos los archivos temporales creados."""
        for file_path in self.temp_files:
            try:
                if os.path.exists(file_path):
                    os.remove(file_path)
            except:
                pass
        self.temp_files = []
    
    def _add_temp_file(self, file_path: str):
        """Registra un archivo temporal para su posterior limpieza."""
        self.temp_files.append(file_path)
        
    def process_pdf(self, input_path: str) -> List[str]:
        """
        Procesa un archivo PDF y genera los documentos limpios.
        
        Args:
            input_path: Ruta al archivo PDF de entrada
            
        Returns:
            Lista de rutas a los archivos PDF procesados
        """
        try:
            # Identificar tareas en el PDF
            tasks = self._identify_tasks(input_path)
            
            output_files = []
            base_name = os.path.splitext(os.path.basename(input_path))[0]
            
            for i, task in enumerate(tasks):
                # Extraer la tarea del PDF
                task_pdf_path = self._extract_task(input_path, task)
                
                if task_pdf_path and os.path.exists(task_pdf_path):
                    # Limpiar el PDF de la tarea
                    cleaned_path = self._clean_task_pdf(task_pdf_path, task)
                    
                    if cleaned_path and os.path.exists(cleaned_path):
                        # Generar nombre de archivo de salida
                        if len(tasks) > 1:
                            # Usar el W/O si está disponible, si no usar índice
                            wo_suffix = task.work_order if task.work_order else f"TASK_{i+1:03d}"
                            output_name = f"{base_name} F_{wo_suffix}.pdf"
                        else:
                            output_name = f"{base_name} F.pdf"
                        
                        output_path = os.path.join(os.path.dirname(cleaned_path), output_name)
                        
                        # Renombrar el archivo limpio al nombre de salida
                        try:
                            if os.path.exists(output_path):
                                os.remove(output_path)
                            os.rename(cleaned_path, output_path)
                            output_files.append(output_path)
                        except Exception as e:
                            print(f"Error al renombrar {cleaned_path} a {output_path}: {e}")
                            # Si falla el renombrado, mantener el archivo con su nombre temporal
                            output_files.append(cleaned_path)
                
                # Limpiar archivo temporal de la tarea extraída
                if task_pdf_path and os.path.exists(task_pdf_path) and task_pdf_path not in output_files:
                    try:
                        os.remove(task_pdf_path)
                    except:
                        pass
            
            return output_files
            
        except Exception as e:
            print(f"Error en process_pdf: {e}")
            raise
    
    def _identify_tasks(self, pdf_path: str) -> List[TaskSection]:
        """
        Identifica las tareas dentro del PDF.
        
        Args:
            pdf_path: Ruta al PDF
            
        Returns:
            Lista de TaskSection identificadas
        """
        tasks = []
        
        try:
            with pdfplumber.open(pdf_path) as pdf:
                current_task = None
                task_start_page = 0
                
                for page_num, page in enumerate(pdf.pages):
                    text = page.extract_text() or ""
                    
                    # Buscar patrones de inicio de tarea
                    task_match = self._find_task_start(text)
                    
                    if task_match:
                        # Si ya hay una tarea abierta, cerrarla
                        if current_task:
                            tasks.append(current_task)
                        
                        # Iniciar nueva tarea
                        current_task = TaskSection(
                            start_page=page_num,
                            end_page=page_num,
                            task_type=task_match['type'],
                            task_name=task_match['name'],
                            work_order=task_match.get('work_order')
                        )
                    elif current_task:
                        # Extender la tarea actual
                        current_task.end_page = page_num
                        
                        # Verificar si la página siguiente podría ser el inicio de una nueva tarea
                        if self._is_task_end(text):
                            tasks.append(current_task)
                            current_task = None
                
                # Agregar la última tarea si existe
                if current_task:
                    tasks.append(current_task)
        except Exception as e:
            print(f"Error identificando tareas: {e}")
            # Si falla la identificación, tratar todo el PDF como una sola tarea
            tasks = [TaskSection(
                start_page=0,
                end_page=None,
                task_type=TaskType.OTHER,
                task_name=os.path.basename(pdf_path),
                work_order=None
            )]
        
        return tasks
    
    def _find_task_start(self, text: str) -> Optional[Dict[str, Any]]:
        """
        Busca el inicio de una tarea en el texto.
        
        Args:
            text: Texto de la página
            
        Returns:
            Diccionario con la información de la tarea o None
        """
        patterns = [
            # Patrón para Task Cards
            {
                'pattern': r'TASK CARD.*?\n.*?Task Card Description:',
                'type': TaskType.TASK_CARD,
                'name_pattern': r'Task Card Description:\s*(.+?)(?:\n|$)'
            },
            # Patrón para Engineering Orders
            {
                'pattern': r'ENGINEERING ORDER.*?\n.*?Description:',
                'type': TaskType.ENGINEERING_ORDER,
                'name_pattern': r'Description:\s*(.+?)(?:\n|$)'
            },
            # Patrón para Daily Checks
            {
                'pattern': r'DAILY CHECK.*?\n.*?Description:',
                'type': TaskType.DAILY_CHECK,
                'name_pattern': r'Description:\s*(.+?)(?:\n|$)'
            },
            # Patrón para Weekly Checks
            {
                'pattern': r'WEEKLY CHECK.*?\n.*?Description:',
                'type': TaskType.WEEKLY_CHECK,
                'name_pattern': r'Description:\s*(.+?)(?:\n|$)'
            }
        ]
        
        for pattern_info in patterns:
            if re.search(pattern_info['pattern'], text, re.IGNORECASE):
                # Extraer nombre de la tarea
                name_match = re.search(
                    pattern_info['name_pattern'],
                    text,
                    re.IGNORECASE | re.DOTALL
                )
                task_name = name_match.group(1).strip() if name_match else "Sin nombre"
                
                # Extraer W/O si existe
                wo_match = re.search(r'W/O:\s*(\d+)', text)
                work_order = wo_match.group(1) if wo_match else None
                
                return {
                    'type': pattern_info['type'],
                    'name': task_name,
                    'work_order': work_order
                }
        
        return None
    
    def _is_task_end(self, text: str) -> bool:
        """
        Determina si una página marca el final de una tarea.
        
        Args:
            text: Texto de la página
            
        Returns:
            True si es el final de una tarea
        """
        # Palabras clave que indican el final de una tarea
        end_patterns = [
            r'END OF TASK',
            r'END OF E\.O\.',
            r'FIN DE LA TAREA',
            r'END OF EO',
            r'--- END ---',
            r'Technician Signature',
            r'TECHNICIAN SIGNATURE',
            r'END OF TASK CARD',
        ]
        
        for pattern in end_patterns:
            if re.search(pattern, text, re.IGNORECASE):
                return True
        
        # Verificar si la página contiene una nueva tarea
        if self._find_task_start(text):
            return True
        
        return False
    
    def _extract_task(self, pdf_path: str, task: TaskSection) -> Optional[str]:
        """
        Extrae una tarea específica del PDF.
        
        Args:
            pdf_path: Ruta al PDF
            task: TaskSection a extraer
            
        Returns:
            Ruta al PDF extraído o None
        """
        try:
            reader = PdfReader(pdf_path)
            writer = PdfWriter()
            
            # Si task.end_page es None, usar la última página
            end_page = task.end_page if task.end_page is not None else len(reader.pages) - 1
            
            start = task.start_page
            end = min(end_page + 1, len(reader.pages))
            
            # Extraer páginas
            for page_num in range(start, end):
                page = reader.pages[page_num]
                text = page.extract_text() or ""
                
                # Si estamos en modo de eliminación de metadatos y la página parece ser de metadatos
                if self.remove_metadata and self._is_metadata_page(text):
                    continue
                
                writer.add_page(page)
            
            if len(writer.pages) == 0:
                return None
            
            # Guardar en archivo temporal
            temp_file = tempfile.NamedTemporaryFile(delete=False, suffix='.pdf')
            temp_path = temp_file.name
            temp_file.close()
            
            with open(temp_path, 'wb') as f:
                writer.write(f)
            
            self._add_temp_file(temp_path)
            return temp_path
            
        except Exception as e:
            print(f"Error extrayendo tarea: {e}")
            return None
    
    def _clean_task_pdf(self, pdf_path: str, task: TaskSection) -> Optional[str]:
        """
        Limpia el PDF de la tarea.
        
        Args:
            pdf_path: Ruta al PDF
            task: TaskSection
            
        Returns:
            Ruta al PDF limpio o None
        """
        try:
            reader = PdfReader(pdf_path)
            writer = PdfWriter()
            
            # Limpiar páginas
            for page in reader.pages:
                text = page.extract_text() or ""
                
                # Omitir páginas de metadatos
                if self.remove_metadata and self._is_metadata_page(text):
                    continue
                
                # Omitir páginas con solo números
                if self._is_only_numbers(text):
                    continue
                
                # Omitir páginas de control con tablas vacías
                if self._is_empty_control_table(text):
                    continue
                
                writer.add_page(page)
            
            # Añadir página en blanco si es necesario
            if self.add_blank_pages and len(writer.pages) % 2 == 1:
                writer.add_blank_page()
            
            if len(writer.pages) == 0:
                return None
            
            # Guardar en archivo temporal
            temp_file = tempfile.NamedTemporaryFile(delete=False, suffix='.pdf')
            temp_path = temp_file.name
            temp_file.close()
            
            with open(temp_path, 'wb') as f:
                writer.write(f)
            
            self._add_temp_file(temp_path)
            return temp_path
            
        except Exception as e:
            print(f"Error limpiando tarea: {e}")
            return None
    
    def _is_metadata_page(self, text: str) -> bool:
        """
        Determina si una página es principalmente metadatos.
        
        Args:
            text: Texto de la página
            
        Returns:
            True si es página de metadatos
        """
        metadata_patterns = [
            r'Revision Control Record',
            r'ELECTRICAL LOAD CHANGE',
            r'PARTS LIST',
            r'REQUIRED EQUIPMENT AND TOOLS',
            r'Component Description:',
            r'Compliance Info:',
            r'Estimated Man Hour',
            r'Maintenance Program Affected',
            r'Quality Control Certification',
            r'Weight and Balance Affected',
            r'Accomplishment Data',
            r'W/O Description',
            r'ATA',
            r'CMR',
            r'RVSM',
            r'Corrosion',
            r'RII',
            r'CDCCL',
            r'Critical Task',
            r'NDT',
            r'Eddy Current Test',
            r'Penetrant Test',
            r'Magnetic Particle Test',
            r'Ultrasonic Test'
        ]
        
        count = sum(1 for pattern in metadata_patterns if re.search(pattern, text, re.IGNORECASE))
        
        # Si tiene más de 3 patrones de metadatos, es página de metadatos
        return count > 3
    
    def _is_only_numbers(self, text: str) -> bool:
        """
        Verifica si una página contiene solo números o números con espacios.
        
        Args:
            text: Texto de la página
            
        Returns:
            True si solo contiene números
        """
        cleaned = re.sub(r'[\s\n\r\t]', '', text)
        return cleaned.isdigit() and len(cleaned) > 0
    
    def _is_empty_control_table(self, text: str) -> bool:
        """
        Verifica si la página contiene tablas vacías o de control.
        
        Args:
            text: Texto de la página
            
        Returns:
            True si es una tabla de control vacía
        """
        lines = [line.strip() for line in text.split('\n') if line.strip()]
        
        # Si hay menos de 3 líneas significativas, probablemente es una tabla vacía
        if len(lines) < 3:
            return True
        
        # Verificar si todas las líneas contienen solo caracteres de tabla
        table_chars = ['|', '-', '+', '=']
        table_lines = 0
        for line in lines:
            if any(char in line for char in table_chars):
                table_lines += 1
        
        # Si más del 70% de las líneas son de tabla, es una tabla vacía
        if len(lines) > 0 and (table_lines / len(lines)) > 0.7:
            return True
        
        return False
