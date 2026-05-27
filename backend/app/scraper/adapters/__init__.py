"""Pasta de adapters por site.

Adicionar um site novo = criar um modulo aqui com uma subclasse de
``BaseAdapter`` E adicionar uma linha ``from . import <nome>`` aqui embaixo.

O import explicito garante que o adapter:
  - eh registrado quando o pacote eh importado (via ``__init_subclass__``);
  - eh incluido por bundlers (PyInstaller) que so seguem imports estaticos —
    o ``pkgutil.iter_modules`` do registry nao enxerga arquivos dentro do
    binario empacotado.
"""

from . import novelbin  # noqa: F401
from . import novelmania  # noqa: F401
from . import novellfull
