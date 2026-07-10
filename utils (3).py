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
        self.temp_files = []
        
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
        Procesa un archivo PDF y genera un único documento limpio.
        
        Args:
            input_path: Ruta al archivo PDF de entrada
            
        Returns:
            Lista con la ruta al archivo PDF procesado (siempre 1 archivo)
        """
        try:
            # Obtener el nombre base del archivo
            base_name = os.path.splitext(os.path.basename(input_path))[0]
            
            # Crear un writer para el documento final
            final_writer = PdfWriter()
            reader = PdfReader(input_path)
            
            # Procesar cada página del PDF
            pages_to_keep = []
            
            # Primero, identificar páginas que NO son de metadatos/control
            for page_num, page in enumerate(reader.pages):
                text = page.extract_text() or ""
                
                # Determinar si la página es útil
                should_keep = self._should_keep_page(text, page_num)
                
                if should_keep:
                    pages_to_keep.append(page)
            
            # Si no hay páginas para mantener, devolver el original
            if not pages_to_keep:
                # Si no se encontraron páginas válidas, usar todo el PDF
                pages_to_keep = [page for page in reader.pages]
            
            # Añadir las páginas seleccionadas al writer final
            for page in pages_to_keep:
                final_writer.add_page(page)
            
            # Añadir página en blanco si es necesario (doble cara)
            if self.add_blank_pages and len(final_writer.pages) % 2 == 1:
                final_writer.add_blank_page()
            
            if len(final_writer.pages) == 0:
                return []
            
            # Guardar en archivo temporal
            temp_file = tempfile.NamedTemporaryFile(delete=False, suffix='.pdf')
            temp_path = temp_file.name
            temp_file.close()
            
            with open(temp_path, 'wb') as f:
                final_writer.write(f)
            
            # Generar nombre de salida
            output_name = f"{base_name} F.pdf"
            output_path = os.path.join(os.path.dirname(temp_path), output_name)
            
            # Renombrar el archivo temporal al nombre de salida
            if os.path.exists(output_path):
                os.remove(output_path)
            os.rename(temp_path, output_path)
            
            self._add_temp_file(output_path)
            
            return [output_path]
            
        except Exception as e:
            print(f"Error en process_pdf: {e}")
            raise
    
    def _should_keep_page(self, text: str, page_num: int = 0) -> bool:
        """
        Determina si una página debe ser conservada en el documento final.
        
        Args:
            text: Texto de la página
            page_num: Número de página (0-based)
            
        Returns:
            True si la página debe ser conservada
        """
        # Limpiar el texto para análisis
        clean_text = text.strip()
        
        # 1. Si la página está vacía, probablemente no es útil
        if not clean_text or len(clean_text) < 20:
            return False
        
        # 2. Si la página contiene solo números (páginas de control)
        if self._is_only_numbers(clean_text):
            return False
        
        # 3. Si la página es principalmente metadatos (W/O Description, etc.)
        if self._is_metadata_page(clean_text):
            return False
        
        # 4. Si la página es una tabla vacía o de control
        if self._is_empty_control_table(clean_text):
            return False
        
        # 5. Si la página contiene contenido de tarea (palabras clave)
        task_keywords = [
            'TASK CARD', 'Task Card', 'Task Card Description',
            'W/O:', 'W/O Description',
            'Perform', 'Procedure', 'Inspection',
            'WARNING:', 'CAUTION:', 'NOTE:',
            'TECHNICIAN', 'INSPECTOR',
            'AMM TASK', 'AMM Ref', 'Manual Reference',
            'Description:', 'Item', 'List of',
            'Job Set-up', 'Close-up', 'Close Up',
            'END OF TASK', 'End of Task'
        ]
        
        for keyword in task_keywords:
            if keyword.lower() in clean_text.lower():
                return True
        
        # 6. Si la página parece contener texto de procedimiento
        # (tiene palabras que indican contenido técnico)
        technical_words = [
            'aircraft', 'engine', 'landing', 'gear', 'brake',
            'inspection', 'check', 'install', 'remove', 'replace',
            'maintenance', 'repair', 'service', 'test', 'verify',
            'ensure', 'make sure', 'observe', 'perform', 'apply',
            'use', 'clean', 'lubricate', 'drain', 'fill', 'check'
        ]
        
        technical_count = sum(1 for word in technical_words if word.lower() in clean_text.lower())
        if technical_count >= 3:
            return True
        
        # 7. Si la página contiene tablas con datos (no solo metadatos)
        table_keywords = ['Pos.', 'S/N', 'Removed', 'Installed', 'Pin Remaining']
        if any(keyword.lower() in clean_text.lower() for keyword in table_keywords):
            if len(clean_text.split()) > 50:  # Suficiente contenido
                return True
        
        # 8. Si la página contiene imágenes o diagramas (no podemos detectar fácilmente,
        # pero si tiene texto suficiente y no es metadatos, la conservamos)
        if len(clean_text.split()) > 100 and not self._is_metadata_page(clean_text):
            return True
        
        # 9. Si la página contiene "P/N" y "Description" (posiblemente lista de partes)
        if 'P/N' in clean_text and 'Description' in clean_text:
            if len(clean_text.split()) > 30:
                return True
        
        # 10. Si contiene "Figure" o "Fig" (diagramas importantes)
        if re.search(r'Figure|Fig\.', clean_text, re.IGNORECASE):
            if len(clean_text.split()) > 20:
                return True
        
        return False
    
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
            r'Ultrasonic Test',
            r'Print Date:',
            r'Doc Control',
            r'Attachment:',
            r'Special Requirements:',
            r'Manual Reference:',
            r'Zone:',
            r'Access:',
            r'Material Required',
            r'List of required material',
            r'List of Materials',
            r'CodePart No.DescriptionQtyCategory',
            r'Concesionaria Vuela Compañía de Aviación',
            r'MAINTENANCE ENGINEERING MANAGEMENT',
            r'GERENCIA DE INGENIERÍA DE MANTENIMIENTO'
        ]
        
        # Contar cuántos patrones de metadatos coinciden
        count = sum(1 for pattern in metadata_patterns if re.search(pattern, text, re.IGNORECASE))
        
        # Si tiene más de 2 patrones de metadatos y no tiene contenido de tarea
        if count > 2:
            # Verificar si tiene contenido de tarea real
            task_content = re.search(r'TASK CARD|Task Card|Perform|Procedure|Inspection|WARNING:', text, re.IGNORECASE)
            if not task_content:
                return True
        
        return False
    
    def _is_only_numbers(self, text: str) -> bool:
        """
        Verifica si una página contiene solo números o números con espacios.
        
        Args:
            text: Texto de la página
            
        Returns:
            True si solo contiene números
        """
        cleaned = re.sub(r'[\s\n\r\t]', '', text)
        if cleaned.isdigit() and len(cleaned) > 0:
            return True
        # También considerar páginas con números secuenciales (1, 2, 3, ...)
        lines = text.strip().split('\n')
        if len(lines) <= 3 and all(re.match(r'^\s*\d+\s*$', line.strip()) for line in lines if line.strip()):
            return True
        return False
    
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
        
        # Si contiene frases típicas de tablas vacías
        empty_patterns = [
            r'ItemDescriptionTechnicianInspector',
            r'TechnicianInspector',
            r'DescriptionTechnicianInspector',
            r'P/NS/NPosition',
            r'P/NS/NPositionNDT',
            r'P/NS/NPositionMagnetic Particle Test',
            r'CodePart No.DescriptionQtyCategory',
            r'CODEDESCRIPTIONP/NQTY',
            r'CODEDESCRIPTIONPRODUCT P/NQTY'
        ]
        
        for pattern in empty_patterns:
            if re.search(pattern, text, re.IGNORECASE):
                return True
        
        return False