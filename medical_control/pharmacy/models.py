from django.db import models
from django.contrib.auth.models import User


# ---------------------------------------------------------------------
# 1. Вспомогательные классы и константы
# ---------------------------------------------------------------------

class TimeStampedModel(models.Model):
    """
    Абстрактная модель для автоматического заполнения дат создания и обновления.
    """
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        abstract = True


# Пример статусов для заказов
class OrderStatus(models.TextChoices):
    DRAFT = 'draft', 'Черновик'
    SENT = 'sent', 'Отправлен'
    RECEIVED = 'received', 'Получен'
    CANCELLED = 'cancelled', 'Отменён'


# Пример статусов для приёмки
class ReceiptStatus(models.TextChoices):
    PENDING = 'pending', 'Ожидается'
    PARTIAL = 'partial', 'Частично принято'
    COMPLETED = 'completed', 'Завершено'
    REJECTED = 'rejected', 'Отклонено'


# Пример статусов для продажи (чека)
class SaleStatus(models.TextChoices):
    OPEN = 'open', 'Открыт'
    COMPLETED = 'completed', 'Оплачен'
    RETURNED = 'returned', 'Возврат'


# ---------------------------------------------------------------------
# 2. Основные справочники
# ---------------------------------------------------------------------

class Product(TimeStampedModel):
    """
    Справочник товаров (лекарственные препараты, парафармация и т.д.)
    """
    name = models.CharField(max_length=255)
    product_code = models.CharField(
        max_length=100,
        unique=True,
        help_text="Штрихкод, внутр. код или код маркировки"
    )
    form = models.CharField(
        max_length=100,
        blank=True,
        help_text="Лекарственная форма (таблетки, капсулы и т.д.)"
    )
    composition = models.TextField(blank=True, help_text="Действующее вещество / состав")
    manufacturer = models.CharField(max_length=255, blank=True)
    is_restricted = models.BooleanField(default=False, help_text="Рецептурный / особый контроль?")
    min_stock_level = models.PositiveIntegerField(default=0, help_text="Минимальный остаток")
    max_stock_level = models.PositiveIntegerField(default=0, help_text="Максимальный остаток")

    def __str__(self):
        return self.name


class Batch(TimeStampedModel):
    """
    Партии (серии) товаров с учётом срока годности.
    """
    product = models.ForeignKey(Product, on_delete=models.CASCADE, related_name='batches')
    batch_number = models.CharField(max_length=100, blank=True)
    expiration_date = models.DateField(blank=True, null=True)

    def __str__(self):
        return f"{self.product.name} | Партия: {self.batch_number}"


class Warehouse(TimeStampedModel):
    """
    Склад / аптечная точка.
    """
    name = models.CharField(max_length=255, help_text="Например, 'Аптека №1 на Ленина'")
    location = models.CharField(max_length=255, blank=True)
    # Можно добавить тип (склад, розничная точка, пункт выдачи и т.д.)
    warehouse_type = models.CharField(max_length=50, blank=True)

    def __str__(self):
        return self.name


class Inventory(TimeStampedModel):
    """
    Учёт остатков (количество товара конкретной партии на складе/в аптеке).
    """
    warehouse = models.ForeignKey(Warehouse, on_delete=models.CASCADE, related_name='inventory')
    product = models.ForeignKey(Product, on_delete=models.CASCADE, related_name='inventory_items')
    batch = models.ForeignKey(Batch, on_delete=models.SET_NULL, blank=True, null=True)
    quantity = models.PositiveIntegerField(default=0, help_text="Текущее количество")
    cost_price = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    retail_price = models.DecimalField(max_digits=10, decimal_places=2, default=0)

    class Meta:
        unique_together = ('warehouse', 'product', 'batch')

    def __str__(self):
        return f"{self.warehouse.name} | {self.product.name} | Остаток: {self.quantity}"


# ---------------------------------------------------------------------
# 3. Поставщики и закупки
# ---------------------------------------------------------------------

class Supplier(TimeStampedModel):
    """
    Поставщик лекарственных препаратов или сопутствующих товаров.
    """
    name = models.CharField(max_length=255)
    contact_info = models.CharField(max_length=255, blank=True)
    address = models.CharField(max_length=255, blank=True)
    inn = models.CharField(max_length=20, blank=True, verbose_name="ИНН")
    ogrn = models.CharField(max_length=20, blank=True, verbose_name="ОГРН")

    def __str__(self):
        return self.name


class PurchaseOrder(TimeStampedModel):
    """
    Заголовок (шапка) заказа поставщику.
    """
    supplier = models.ForeignKey(Supplier, on_delete=models.CASCADE, related_name='purchase_orders')
    warehouse = models.ForeignKey(Warehouse, on_delete=models.CASCADE, related_name='purchase_orders')
    order_date = models.DateTimeField(auto_now_add=True)
    status = models.CharField(
        max_length=20,
        choices=OrderStatus.choices,
        default=OrderStatus.DRAFT
    )
    total_cost = models.DecimalField(max_digits=12, decimal_places=2, default=0)

    def __str__(self):
        return f"Заказ #{self.id} от {self.order_date.date()}"


class PurchaseOrderDetail(TimeStampedModel):
    """
    Детали заказа поставщику (строки).
    """
    purchase_order = models.ForeignKey(
        PurchaseOrder,
        on_delete=models.CASCADE,
        related_name='order_details'
    )
    product = models.ForeignKey(Product, on_delete=models.CASCADE)
    quantity = models.PositiveIntegerField(default=0)
    price = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    discount = models.DecimalField(
        max_digits=6,
        decimal_places=2,
        default=0,
        help_text="Скидка, если есть"
    )

    def __str__(self):
        return f"Товар: {self.product.name}, Кол-во: {self.quantity}"


# ---------------------------------------------------------------------
# 4. Приёмка товаров
# ---------------------------------------------------------------------

class GoodsReceipt(TimeStampedModel):
    """
    Документ приёмки товаров по заказу или без него.
    """
    purchase_order = models.ForeignKey(
        PurchaseOrder,
        on_delete=models.SET_NULL,
        blank=True, null=True,
        related_name='goods_receipts'
    )
    warehouse = models.ForeignKey(Warehouse, on_delete=models.CASCADE, related_name='goods_receipts')
    receipt_date = models.DateTimeField(auto_now_add=True)
    status = models.CharField(
        max_length=20,
        choices=ReceiptStatus.choices,
        default=ReceiptStatus.PENDING
    )

    def __str__(self):
        return f"Приёмка #{self.id} от {self.receipt_date.date()}"


class GoodsReceiptDetail(TimeStampedModel):
    """
    Детали приёмки (полученные товары и их партии).
    """
    goods_receipt = models.ForeignKey(
        GoodsReceipt,
        on_delete=models.CASCADE,
        related_name='receipt_details'
    )
    product = models.ForeignKey(Product, on_delete=models.CASCADE)
    batch = models.ForeignKey(Batch, on_delete=models.SET_NULL, blank=True, null=True)
    quantity = models.PositiveIntegerField(default=0)
    cost_price = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    expiration_date = models.DateField(blank=True, null=True)

    def __str__(self):
        return f"Приёмка #{self.goods_receipt.id}: {self.product.name}"


# ---------------------------------------------------------------------
# 5. Продажи
# ---------------------------------------------------------------------

class Customer(TimeStampedModel):
    """
    Клиент/пациент, если нужна система лояльности или учёт постоянных покупателей.
    """
    name = models.CharField(max_length=100, blank=True)
    surname = models.CharField(max_length=100, blank=True)
    phone = models.CharField(max_length=20, blank=True)
    email = models.EmailField(blank=True)
    discount_card_number = models.CharField(max_length=50, blank=True)

    def __str__(self):
        return f"{self.name} {self.surname}"


class Sale(TimeStampedModel):
    """
    Шапка (чек) продажи.
    """
    warehouse = models.ForeignKey(Warehouse, on_delete=models.CASCADE, related_name='sales')
    cashier = models.ForeignKey(User, on_delete=models.SET_NULL, blank=True, null=True)
    customer = models.ForeignKey(Customer, on_delete=models.SET_NULL, blank=True, null=True)
    sale_date = models.DateTimeField(auto_now_add=True)
    status = models.CharField(
        max_length=20,
        choices=SaleStatus.choices,
        default=SaleStatus.OPEN
    )
    total_amount = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    payment_type = models.CharField(
        max_length=50,
        default='cash',
        help_text="наличные / карта / смешанная и т.д."
    )

    def __str__(self):
        return f"Продажа #{self.id} от {self.sale_date}"


class SaleDetail(TimeStampedModel):
    """
    Позиции в чеке продажи.
    """
    sale = models.ForeignKey(Sale, on_delete=models.CASCADE, related_name='sale_details')
    product = models.ForeignKey(Product, on_delete=models.CASCADE)
    batch = models.ForeignKey(Batch, on_delete=models.SET_NULL, blank=True, null=True)
    quantity = models.PositiveIntegerField(default=1)
    unit_price = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    discount = models.DecimalField(max_digits=6, decimal_places=2, default=0)

    def __str__(self):
        return f"Продажа #{self.sale.id}: {self.product.name}"


# ---------------------------------------------------------------------
# 6. Списания / Возвраты
# ---------------------------------------------------------------------

class WriteOff(TimeStampedModel):
    """
    Документ списания или возврата товара (например, просрочка, брак).
    """
    warehouse = models.ForeignKey(Warehouse, on_delete=models.CASCADE, related_name='write_offs')
    product = models.ForeignKey(Product, on_delete=models.CASCADE)
    batch = models.ForeignKey(Batch, on_delete=models.SET_NULL, blank=True, null=True)
    quantity = models.PositiveIntegerField(default=0)
    reason = models.CharField(max_length=255, blank=True, help_text="Причина списания (просрочка, брак и т.д.)")

    def __str__(self):
        return f"Списание #{self.id}: {self.product.name} - {self.quantity} шт."
