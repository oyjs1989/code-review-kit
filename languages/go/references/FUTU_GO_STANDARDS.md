# FUTU Go Coding Standards

**Version**: 2.1.0
**Last Updated**: 2026-01-23
**Owner**: FUTU Development Team

This document contains the complete Go coding standards for FUTU projects. All specialized review skills reference these standards.

**Total Rules**: 142 (P0: 38, P1: 94, P2: 10)

## Table of Contents

- [P0 Rules - Must Follow](#p0-rules---must-follow)
  - [1.1 Error Handling](#11-error-handling)
  - [1.2 Nil Pointer Safety](#12-nil-pointer-safety)
  - [1.3 Database Operations (GORM)](#13-database-operations-gorm)
  - [1.4 Concurrency Control](#14-concurrency-control)
  - [1.5 JSON Processing](#15-json-processing)
  - [1.6 Code Simplicity](#16-code-simplicity)
- [P1 Rules - Strongly Recommended](#p1-rules---strongly-recommended)
  - [2.1 Naming Conventions](#21-naming-conventions)
  - [2.2 Logging Standards](#22-logging-standards)
  - [2.3 Code Organization](#23-code-organization)
  - [2.4 Interface Design](#24-interface-design)
  - [2.5 Code Quality](#25-code-quality)
- [P2 Rules - Suggested](#p2-rules---suggested)
  - [3.1 Project Structure](#31-project-structure)
  - [3.2 Testing Standards](#32-testing-standards)
  - [3.3 Configuration Management](#33-configuration-management)
- [P1 Rules - Design Philosophies](#p1-rules---design-philosophies)
  - [4.1 KISS Principle](#41-kiss-principle)
  - [4.2 DRY Principle](#42-dry-principle)
  - [4.3 YAGNI Principle](#43-yagni-principle)
  - [4.4 SOLID Principles](#44-solid-principles)
  - [4.5 Law of Demeter](#45-law-of-demeter)
  - [4.6 Composition Over Inheritance](#46-composition-over-inheritance)
  - [4.7 Less is Exponentially More](#47-less-is-exponentially-more)
  - [4.8 Explicit Over Implicit](#48-explicit-over-implicit)

---

## P0 Rules - Must Follow

### 1.1 Error Handling

**1.1.1** Errors must be wrapped and preserve stack trace
- ❌ Forbidden: `fmt.Errorf("operation failed")`
- ✅ Use: `errors.Errorf()` for creating new errors, `errors.Wrapf(err, "operation failed")` or `errors.WithMessage(err, "operation failed")` for wrapping errors
- ✅ Use `errors.Errorf()` instead of `fmt.Errorf()` for creating new errors
- ❌ Forbidden: `fmt.Sprintf()` or `fmt.Errorf()` for simple error formatting
- If outer layer already uses `errors.WithMessage`, inner layer doesn't need to wrap again

**1.1.2** Error must be in the last return position
- ✅ `func Foo() (result Type, err error)`

**1.1.3** Business functions must return error, not panic
- ❌ Forbidden: `panic("error occurred")`
- ✅ Use: `return errors.New("error occurred")`

**1.1.4** Errors must be checked and handled immediately

**1.1.5** All error types from external interfaces must be handled
When calling external interfaces or APIs, all error types and error codes returned by the interface must be handled. Cannot ignore any error cases.
- Parse all error types and error codes provided by the interface
- Each error type must have corresponding handling logic
- Cannot handle only part of errors, ignoring other error cases
- For unknown errors, must have default handling logic

**Applicable scenarios:**
- Calling third-party APIs or service interfaces
- Processing error responses from external systems
- Scenarios requiring distinction between different error types

**1.1.6** Use appropriate error creation methods
When creating new errors, choose the appropriate method based on whether parameters are needed.
- ✅ With parameters: Use `errors.Errorf("message with %s", param)`
- ✅ Plain text: Use `errors.New("message")`
- ❌ Forbidden: Use `fmt.Errorf()` for creating errors

```go
// ✅ Correct: Use errors.New for plain text
if platformDetails == "" {
    return errors.New("platform details is empty")
}

// ✅ Correct: Use errors.Errorf with parameters
if osType == "" {
    return errors.Errorf("os type not found for platform details: %s", platformDetails)
}

// ❌ Incorrect: Use fmt.Errorf
if osType == "" {
    return fmt.Errorf("os type not found for platform details: %s", platformDetails)
}
```

---

### 1.2 Nil Pointer Safety

**1.2.1** Must check nil before using pointers
```go
if ptr != nil {
    value := *ptr
}
```

---

### 1.3 Database Operations (GORM)

**1.3.1** Queries must explicitly specify Where conditions
- ✅ `db.Where("id = ?", id).Find(&result)`
- ✅ If there are no query conditions, Where clause can be omitted
- Query conditions should be explicit, cannot rely on implicit dependencies

**1.3.2** Queries must explicitly specify Select columns (except constant definitions)
- ❌ Forbidden: `SELECT *`
- ✅ Use: `db.Select("id, name, status").Find(&result)`
- ✅ Only query fields that are actually used (e.g., if only `Detail` is used, only query `detail`)
- ✅ Use different structs to read different select contents
- ✅ If only `role_id` is used, only query `role_id`, not the entire row

**1.3.3** Use fluent method chaining for readability and error handling

Chain GORM methods together and assign error at the end for better readability:
```go
// ✅ Recommended: Fluent chaining with error at end
err = db.Model(&model.TagValue{}).
    Select("id, `key`, value, status, sync_status, create_time, update_time, creator, modifier").
    Where(query).
    Offset(int(offset)).
    Limit(int(limit)).
    Find(&tagValueList).Error

// ❌ Avoid: Breaking chain to check intermediate errors (unless necessary)
query := db.Model(&model.TagValue{})
query = query.Select("id, name")
if err := query.Where(condition).Error; err != nil {
    return err
}
```

**1.3.4** Do not use `Save()` method
- ❌ Forbidden: `db.Save(&model)`
- ✅ Use: `db.Updates(&model)` or `db.Create(&model)`

**1.3.5** Prefer `Take()` over `First()`
- `First()` sorts by primary key (worse performance)
- `Take()` doesn't sort (better performance)

**1.3.6** GORM tags must explicitly specify column
```go
type Model struct {
    ID   int64  `gorm:"column:id"`
    Name string `gorm:"column:name"`
}
```

**1.3.7** All struct fields must be used in business logic

Every field defined in a struct MUST be used somewhere in the business flow from creation to completion. During code review, trace the entire business flow to verify all fields are utilized.

**Critical Review Process:**
1. Identify all fields in the struct definition
2. Trace business flow from creation to end
3. Verify each field is read/written at least once
4. Flag any unused fields for removal

```go
// ❌ Problem: UnusedField and Description are never used
type TagKey struct {
    ID          int64  `gorm:"column:id"`
    Key         string `gorm:"column:key"`
    Name        string `gorm:"column:name"`
    UnusedField string `gorm:"column:unused_field"` // ⚠️ Never used in business logic
    Description string `gorm:"column:description"`   // ⚠️ Never read or written
}

// ✅ Solution: Remove unused fields or use them properly
type TagKey struct {
    ID   int64  `gorm:"column:id"`
    Key  string `gorm:"column:key"`
    Name string `gorm:"column:name"`
}
```

**When to flag as issue:**
- Field is defined but never set in Create/Update operations
- Field is queried but never used in business logic
- Field exists only for "future use" (violates YAGNI principle)

**Exceptions (fields that don't require usage tracking):**
- Audit fields: `CreateTime`, `UpdateTime`, `Creator`, `Modifier` (system-managed)
- Soft delete: `DeleteTime`, `IsDeleted` (framework-managed)

**1.3.8** GORM struct field ordering for database models

Fields should follow this priority order for readability and consistency:
1. **ID field** - Always first
2. **Business fields** - Ordered by usage frequency (most used first)
3. **Creator/Modifier** - User tracking fields
4. **CreateTime/UpdateTime** - Timestamp fields last

```go
// ✅ Recommended: Proper field ordering
type TagKeyForQuery struct {
    // 1. ID field first
    ID         int64                      `gorm:"column:id"`

    // 2. Business fields by priority (most commonly used first)
    Key        string                     `gorm:"column:key"`
    Name       string                     `gorm:"column:name"`
    Status     constants.TagStatus        `gorm:"column:status"`
    SyncStatus constants.TagKeySyncStatus `gorm:"column:sync_status"`
    Editable   bool                       `gorm:"column:editable"`
    Remark     *string                    `gorm:"column:remark"`

    // 3. User tracking fields
    Creator    string                     `gorm:"column:creator"`
    Modifier   string                     `gorm:"column:modifier"`

    // 4. Timestamp fields last
    CreateTime time.Time                  `gorm:"column:create_time"`
    UpdateTime time.Time                  `gorm:"column:update_time"`
}

// ❌ Avoid: Random field ordering
type TagKeyForQuery struct {
    Name       string    `gorm:"column:name"`
    UpdateTime time.Time `gorm:"column:update_time"`
    ID         int64     `gorm:"column:id"`
    Creator    string    `gorm:"column:creator"`
    // ... fields in random order
}
```

**1.3.9** Use ID to locate records for updates and deletes
When updating or deleting records, use primary key ID to locate records, not other fields.
- ❌ Should not use other fields to locate records, should use `id`
- ✅ Using primary key ensures uniqueness and performance
- ❌ Avoid using non-primary key fields for update or delete operations

```go
// ✅ Correct: Use ID to locate record
err := db.Where("id = ?", id).Updates(&user).Error

// ❌ Incorrect: Use other field to locate record
err := db.Where("name = ?", name).Updates(&user).Error
```

**1.3.10** Use batch operations with lists
When creating or deleting records in batch, use list operations at once, not individual operations in loops.
- ✅ Use a list to batch create, no need for `create` in loop
- ✅ Batch delete: `db.Where("id in ?", idList).Delete(&xxx)`
- ⚠️ CRUD operations in transactions can also fail, all need error handling

```go
// ✅ Correct: Batch create
users := []User{user1, user2, user3}
err := db.Create(&users).Error

// ❌ Incorrect: Create in loop
for _, user := range users {
    err := db.Create(&user).Error  // Poor performance
    if err != nil {
        return err
    }
}
```

**1.3.11** Index naming conventions
Database index names should follow unified conventions, regular indexes and unique indexes use different prefixes.
- ✅ Regular index: `idx_xxx`
- ✅ Unique index: `uk_xxx`
- Index names should clearly express the purpose of the index

**1.3.12** Use orm.Slice for list operations
When processing list data, use `orm.Slice` provided methods instead of manual processing.
- ✅ List already provides `orm.Slice`, should use it
- ❌ Avoid manually implementing list operations
- ✅ Use framework-provided utility methods

**1.3.13** Use `tx` naming for transactions
When opening a transaction, the transaction object should use `tx` naming, not `db`.
- ✅ Opening transaction uses `tx` naming
- ✅ Operations within transaction should use `tx` not `db`
- ✅ Clearly distinguish transaction operations from normal operations

```go
// ✅ Correct: Use tx naming
err := db.Transaction(func(tx *gorm.DB) error {
    if err := tx.Create(&user).Error; err != nil {
        return err
    }
    return tx.Create(&profile).Error
})

// ❌ Incorrect: Use db in transaction
err := db.Transaction(func(tx *gorm.DB) error {
    if err := db.Create(&user).Error; err != nil {  // Should use tx
        return err
    }
    return nil
})
```

---

### 1.4 Concurrency Control

**1.4.1** Use `recovered.ErrorGroup` for concurrent operations
```go
errGroup := recovered.NewErrorGroup()
```

**1.4.2** Use limiter for concurrency control
```go
l := limiter.NewConcurrentLimiter(count)
```

---

### 1.5 JSON Processing

**1.5.1** Do not construct JSON via string concatenation or formatting
- ❌ Forbidden: `fmt.Sprintf(\`{"name": "%s"}\`, name)`
- ✅ Use: `json.Marshal(data)`

**1.5.2** Do not directly fmt JSON structure for structs
Struct JSON serialization should use standard `json` package, cannot directly use `fmt` to print JSON structure.
- ✅ Struct serialization must use `json.Marshal` or `json.Encoder`
- ❌ Forbidden: `fmt.Printf("%+v", struct)` to output struct
- ✅ JSON serialization should be done through standard library

```go
// ✅ Correct: Use json.Marshal
data, err := json.Marshal(user)
if err != nil {
    return err
}
log.Info(string(data))

// ❌ Incorrect: Use fmt to print struct
log.Info(fmt.Sprintf("%+v", user))
```

---

### 1.6 Code Simplicity

**1.6.1** Avoid magic numbers and strings

**1.6.2** Allow pointer passing when data is already pointer type
```go
// ✅ Data is already pointer, pass directly
type User struct {
    Profile *UserProfile
}

func ProcessUser(user *User) {
    SaveProfile(user.Profile) // ✅ OK to pass nil if function accepts it
}
```

**1.6.3** Use proto utility functions
When constructing protobuf messages, should use `proto.XXX()` utility functions.
- ✅ Construct pb messages using `proto.XXX()`, e.g., `proto.Int64(roleDepart.ID)`
- ✅ Use `proto.String()`, `proto.Int64()` and other methods
- ❌ Avoid direct assignment, using utility functions is safer

```go
// ✅ Correct: Use proto utility functions
pb := &UserPB{
    ID:   proto.Int64(user.ID),
    Name: proto.String(user.Name),
}

// ❌ Incorrect: Direct assignment
pb := &UserPB{
    ID:   &user.ID,  // May have issues
    Name: &user.Name,
}
```

**1.6.4** Avoid duplicate implementations
If there are already other conversion functions or utility functions, should reuse them instead of re-implementing.
- ✅ If there are already other conversion functions, should use them
- ❌ Avoid re-implementing the same functionality
- ✅ Maintain code consistency

**1.6.5** Use cache reasonably
Not all data needs caching, should decide whether to use cache based on business requirements.
- ✅ Cache should be used for scenarios that truly need performance improvement
- ❌ Avoid overusing cache
- ✅ For example, favorites don't need redis cache, can directly read/write db

**1.6.6** Avoid unnecessary pointer operations
Avoid unnecessary "address-of followed by dereference" patterns. Use values directly when possible.

**核心原则**:
- ✅ Use values directly when pointer conversion is unnecessary
- ❌ Avoid `&variable` followed immediately by `*variable` pattern

**错误示例**:
```go
// ❌ 不必要的指针操作
approvalCode = &approvalCodeStr
log.String("approval_code", *approvalCode)  // 立即解引用
```

**正确示例**:
```go
// ✅ 直接使用值
approvalCode := approvalCodeStr
log.String("approval_code", approvalCode)
```

**例外**: 需要表达"可选"语义(nil判断)或需要修改原值时,使用指针有意义。

**1.6.7** Optimize code execution order with Early Return
Code execution order should follow the "fail fast" principle. Handle error cases and edge conditions first, then process the main logic. This reduces nesting depth and improves code readability.

**核心原则**:
- ✅ Error conditions and edge cases should return early
- ✅ Keep the main success path at the lowest indentation level (Golden Path)
- ✅ Reduce nesting depth to improve readability
- ❌ Avoid deep nesting of if-else blocks

**错误示例 - 深度嵌套**:
```go
func ProcessUser(user *User) error {
    if user != nil {
        if user.IsActive {
            if user.HasPermission("write") {
                if !user.IsBlocked {
                    // Main logic deeply nested
                    return saveUser(user)
                } else {
                    return errors.New("user is blocked")
                }
            } else {
                return errors.New("no write permission")
            }
        } else {
            return errors.New("user not active")
        }
    } else {
        return errors.New("user is nil")
    }
}
```

**正确示例 - Early Return**:
```go
func ProcessUser(user *User) error {
    // Handle error cases first (fail fast)
    if user == nil {
        return errors.New("user is nil")
    }
    if !user.IsActive {
        return errors.New("user not active")
    }
    if !user.HasPermission("write") {
        return errors.New("no write permission")
    }
    if user.IsBlocked {
        return errors.New("user is blocked")
    }

    // Main logic at lowest indentation (Golden Path)
    return saveUser(user)
}
```

**优化执行顺序原则**:
1. **廉价检查优先**: 先执行开销小的检查（如 nil 检查、简单比较）
2. **常见失败优先**: 先检查最可能失败的条件
3. **避免无效计算**: 在执行昂贵操作前完成所有前置检查

**执行顺序优化示例**:
```go
// ❌ 不佳 - 昂贵操作在前
func ValidateAndProcess(id int64) error {
    // 昂贵的数据库查询
    user, err := db.GetUserByID(id)
    if err != nil {
        return err
    }

    // 简单检查应该在前面
    if id <= 0 {
        return errors.New("invalid id")
    }

    return processUser(user)
}

// ✅ 正确 - 廉价检查优先
func ValidateAndProcess(id int64) error {
    // 先做简单的参数验证
    if id <= 0 {
        return errors.New("invalid id")
    }

    // 参数有效后再执行昂贵操作
    user, err := db.GetUserByID(id)
    if err != nil {
        return err
    }

    return processUser(user)
}
```

**循环中的 Early Continue**:
```go
// ❌ 不佳 - 深度嵌套
for _, user := range users {
    if user.IsActive {
        if !user.IsBlocked {
            if user.Age >= 18 {
                // Process logic deeply nested
                processUser(user)
            }
        }
    }
}

// ✅ 正确 - Early Continue
for _, user := range users {
    if !user.IsActive {
        continue
    }
    if user.IsBlocked {
        continue
    }
    if user.Age < 18 {
        continue
    }

    // Main logic at lowest indentation
    processUser(user)
}
```

**实际收益**:
- 📖 **可读性提升**: 主流程一目了然，无需追踪复杂的 if-else 嵌套
- 🐛 **降低错误率**: 减少嵌套深度，降低逻辑错误风险
- ⚡ **性能优化**: 快速失败，避免不必要的计算
- 🔧 **易于维护**: 条件清晰分离，添加新检查更容易

**1.6.8** Prefer direct return over assignment with named returns
When returning errors, prefer direct `return` statements over assigning to named return values then returning. Even when `defer` uses the named return value, direct returns are simpler and clearer.

**核心原则**:
- ✅ Use direct `return err` instead of assigning then returning
- ✅ Defer can access directly returned values correctly
- ❌ Avoid `err = errors.New(...); return` pattern

**错误示例**:
```go
func ProcessRequest(ctx context.Context, req *Request) (err error) {
    // ❌ 赋值后 return
    if req.GetBizId() == "" {
        err = errors.New("biz_id is required")
        return
    }

    if req.GetAlias() == "" {
        err = errors.New("alias is required")
        return
    }

    return nil
}
```

**正确示例**:
```go
func ProcessRequest(ctx context.Context, req *Request) (err error) {
    // ✅ 直接 return
    if req.GetBizId() == "" {
        return errors.New("biz_id is required")
    }

    if req.GetAlias() == "" {
        return errors.New("alias is required")
    }

    return nil
}
```

**Defer 场景示例**:
```go
// ✅ 即使有 defer，也应该直接 return
func SaveData(ctx context.Context, data *Data) (err error) {
    defer func() {
        if err != nil {
            log.Error(ctx, "save failed", log.ErrorField(err))
        }
    }()

    if data == nil {
        return errors.New("data is nil")  // ✅ defer 能正确获取
    }

    return db.Save(data)
}

// ❌ 不推荐
func SaveData(ctx context.Context, data *Data) (err error) {
    defer func() {
        if err != nil {
            log.Error(ctx, "save failed", log.ErrorField(err))
        }
    }()

    if data == nil {
        err = errors.New("data is nil")  // ❌ 不必要的赋值
        return
    }

    err = db.Save(data)
    return
}
```

**Note**: Even when `defer` reads or modifies the error, direct `return` works correctly because `defer` executes after the return value is set.

---

## P1 Rules - Strongly Recommended

### 2.1 Naming Conventions

**2.1.1** Structs: CamelCase, first letter uppercase
- ✅ `type UserAccount struct {}`

**2.1.2** Struct fields: CamelCase matching tags
```go
type Model struct {
    UserName  string `gorm:"column:user_name"`
    ProductID int64  `gorm:"column:product_id"`
}
```

**2.1.3** Functions/Methods: CamelCase
- Public: First letter uppercase `GetUserByID()`
- Private: First letter lowercase `getUserByID()`

**2.1.4** Constants: ALL_CAPS with underscores
```go
const (
    MAX_RETRY_COUNT = 3
    DEFAULT_TIMEOUT = 30
)
```

**2.1.5** ID abbreviation always uppercase
- ✅ `UserID`, `ProductID`
- ❌ `UserId`, `ProductId`

**2.1.6** Avoid magic numbers and strings - define constants

**2.1.7** Avoid multiple naming styles for same concept
- ✅ Consistent: `CloudTencent`, `CloudAliyun`, `CloudAws`
- ❌ Mixed: `TencentCloud`, `AliyunCloud`, `CloudAws`

**2.1.8** Business field naming should be unambiguous
```go
type Model struct {
    ID         int64  `gorm:"column:id"`          // table primary key
    TemplateID string `gorm:"column:template_id"` // cloud provider ID
    TemplateTid int64 `gorm:"column:template_tid"` // related table ID
}
```

**2.1.9** Variable names should be descriptive
- ❌ Avoid: `a`, `tmp`, `x`
- ✅ Use: `userCount`, `templateList`, `configMap`

**2.1.10** Interface names usually end with -er
- ✅ `Reader`, `Writer`, `Processor`

**2.1.11** Opposite operations must correspond strictly
- ✅ `Enable` ↔ `Disable`
- ✅ `Start` ↔ `Stop`
- ✅ `Open` ↔ `Close`

**2.1.12** Method names for getting lists use GetList or Search
- ❌ `Get()` - implies single item
- ✅ `GetList()`, `Search()` - implies multiple items

**2.1.13** Struct receiver names should maintain struct characteristics
Struct method receiver names should reflect the struct's characteristics, use meaningful abbreviations.
- ✅ Receiver names maintain struct characteristics, e.g., `mgr` or `m` (for Manager)
- ✅ Receiver names should be concise but meaningful
- ❌ Avoid overly short names (like single letters `a`, `b`)

```go
// ✅ Correct: Receiver name reflects struct characteristics
type UserManager struct {}

func (mgr *UserManager) CreateUser() error {
    // ...
}

// ❌ Incorrect: Receiver name has no meaning
type UserManager struct {}

func (u *UserManager) CreateUser() error {
    // ...
}
```

**2.1.14** Names must match comments
Code naming must be consistent with comments, comments should clearly describe the code's purpose.
- ❌ When name doesn't match comment, need to fix name or comment
- ❌ Comments cannot be too simple, should explain clearly
- ✅ Names and comments should complement each other and remain consistent

---

### 2.2 Logging Standards

**2.2.1** Log fields use snake_case
- ❌ `log.String("UserName", name)`
- ✅ `log.String("user_name", name)`

**2.2.2** Log fields use explicit types (except arrays, structs, maps use log.Any)
- ❌ `log.Any("count", len(list))`
- ✅ `log.Int("count", len(list))`

**2.2.3** Logs must include key context
Logs must include necessary context fields for problem tracking and debugging. Logs are for developers to read, should clearly show what operation is being performed and what the context is.
- ✅ Logs missing necessary fields must be supplemented
- ✅ Use typed log methods like `log.Int32("role_id", role.ID)`
- ✅ Logs should include key information about the operation

```go
// ✅ Correct: Include necessary fields
log.Info(ctx, "operation success",
    log.String("user_id", userID),
    log.Int64("resource_id", resourceID),
    log.Int32("role_id", role.ID))

// ❌ Incorrect: Missing necessary fields
log.Info(ctx, "operation success")
```

**2.2.3.1** Log messages must describe business operations clearly
Log messages (msg field) must clearly describe what business operation the current method is performing. Messages should have business meaning so that the entire process flow and problems can be understood from logs alone without reading code.

Core Principles:
- ✅ Log msg should describe what business operation is being performed, not just technical actions
- ✅ Messages should be understandable to someone unfamiliar with the code
- ✅ Logs should tell a story of the business flow from start to finish
- ✅ Error logs must clearly describe what went wrong in business terms

```go
// ✅ Good: Business-meaningful messages
log.Info(ctx, "starting user registration process",
    log.String("email", email),
    log.String("user_type", userType))

log.Info(ctx, "validating user registration data",
    log.String("email", email))

log.Info(ctx, "creating user account in database",
    log.String("email", email))

log.Info(ctx, "sending welcome email to new user",
    log.String("email", email))

log.Info(ctx, "user registration completed successfully",
    log.String("user_id", userID),
    log.String("email", email))

// ❌ Bad: Technical or vague messages
log.Info(ctx, "success")  // What succeeded?

log.Info(ctx, "processing")  // Processing what?

log.Info(ctx, "database operation")  // What kind of operation?

log.Info(ctx, "calling external API")  // Which API? For what purpose?

// ✅ Good: Error messages with business context
log.Error(ctx, "user registration failed: email already exists in system",
    log.String("email", email),
    log.ErrorField(err))

log.Error(ctx, "failed to send welcome email after user creation",
    log.String("user_id", userID),
    log.String("email", email),
    log.ErrorField(err))

// ❌ Bad: Technical error messages without business context
log.Error(ctx, "query failed", log.ErrorField(err))

log.Error(ctx, "error occurred", log.ErrorField(err))
```

**Benefits of business-meaningful log messages:**
- 📖 **Troubleshooting**: Understand business flow without reading code
- 🐛 **Debugging**: Quickly identify where in the business process failures occur
- 📊 **Monitoring**: Track business operations and identify bottlenecks
- 📝 **Documentation**: Logs serve as runtime documentation of business processes

**2.2.4** Functions should have necessary info/debug logs (non-trivial functions)

**2.2.5** Data layer must not log - logging should be in business logic layer

**2.2.6** Error logs must include ErrorField at the end
```go
log.Error(ctx, "operation failed",
    log.String("user_id", userID),
    log.ErrorField(err))  // error field at the end
```

**2.2.7** Method entry and exit must log
- Entry: log input parameters (non-sensitive)
- Exit: log key execution information
- Important method calls: log input and return values

**2.2.8** Early returns that skip logic must log (only when NOT returning error)
When a method skips subsequent logic due to conditions and returns successfully (nil error), log the reason before returning. **Exception**: If returning an error, no additional log needed as outer layer will log the error.
```go
// ❌ Problem - silent successful early return
func ProcessOrder(ctx context.Context, order *Order) error {
    if order.Status == StatusCompleted {
        return nil // Why did we skip processing? No visibility!
    }

    // main processing logic...
}

// ✅ Fix - log before successful early return
func ProcessOrder(ctx context.Context, order *Order) error {
    if order.Status == StatusCompleted {
        log.Info(ctx, "order already completed, skipping processing",
            log.Int64("order_id", order.ID),
            log.String("status", order.Status))
        return nil // Returning nil = success, need log
    }

    // main processing logic...
}

// ✅ No log needed - returning error (outer layer will log)
func ProcessOrder(ctx context.Context, order *Order) error {
    if order == nil {
        return errors.New("order is nil") // Error return, no log needed here
    }

    if order.Status == StatusInvalid {
        return errors.Errorf("invalid order status: %s", order.Status) // Error logged by caller
    }

    // main processing logic...
}

// ✅ Another example - validation skip
func ValidateAndProcess(ctx context.Context, data *Data) error {
    if data.SkipValidation {
        log.Info(ctx, "validation skipped by flag",
            log.String("data_id", data.ID),
            log.Bool("skip_validation", true))
        return processDirectly(ctx, data) // Skipping normal flow, need log
    }

    // normal validation flow...
}
```

---

### 2.3 Code Organization

**2.3.1** Embedded structs must be at the top
```go
type Model struct {
    orm.BaseModel  // embedded at top
    Name   string
    Status int
}
```

**2.3.2** JSON tags should relate to field names

**2.3.3** Use make to initialize map/slice (except unmarshal/scan)
```go
slice := make([]string, 0, capacity)
m := make(map[string]int, capacity)
```

**2.3.4** Specify capacity when size is known
```go
result := make([]Item, 0, len(sourceList))
```

**2.3.5** Switch must have default branch
```go
switch status {
case StatusActive:
    return "active"
default:
    return "unknown"
}
```

**2.3.6** Don't use iota - specify values explicitly
```go
const (
    StatusEnable  = 0
    StatusDisable = 1
)
```

**2.3.7** No global variables (except unit tests, pre-compiled regex)

**2.3.8** No init functions (except server package service registration)

**2.3.9** Function encapsulation must be meaningful

**2.3.10** NOTE/TODO must include owner
```go
// TODO(zhangsan): optimize performance
// NOTE(lisi): temporary solution, refactor later
```

**2.3.11** Chain calls should break lines for readability
```go
db.Select("id, name").
    Where("status = ?", 1).
    Order("created_at DESC").
    Find(&result)
```

**2.3.15** Clear business layering with clear responsibilities
Code must be organized according to business layers, each layer has clear responsibilities, cannot arbitrarily add new layers.
- ✅ Business layering does not add new layers (e.g., ACL layer), should be placed in `pkg` or `biz`
- ❌ `pkg` package cannot call `repo` layer
- ❌ `pb` cannot directly read/write database, must go through data layer conversion
- ✅ Each layer only handles things within its own responsibility scope

```go
// ✅ Correct: Business logic in biz layer
// biz/user.go
type UserService struct {
    repo UserRepo
}

func (s *UserService) CreateUser(ctx context.Context, req *CreateUserReq) error {
    // business logic
    return s.repo.Create(ctx, user)
}

// ❌ Incorrect: Call repo in pkg
// pkg/user.go
func CreateUser(repo UserRepo) error {
    return repo.Create(ctx, user) // pkg should not depend on repo
}
```

**2.3.16** Interface definitions don't need separate package
Interface definitions should be placed together with implementations, or where the interface is used, don't need to create a separate package for interfaces.
- ❌ `interface` doesn't need a separate `package`
- ✅ Interface definitions should be placed where they are used, or together with implementations
- ❌ Avoid creating additional package structure just for interfaces

---

### 2.4 Interface Design

**2.4.1** Interfaces follow minimal principle

**2.4.2** Repeated parameters can be defined in constructor

**2.4.3** ctx parameter required if using ctx
- ✅ If function uses `ctx`, upper layer must pass it in, cannot ignore
- ✅ Context should be passed throughout the entire call chain
- ❌ Cannot ignore Context parameter

**2.4.4** ctx as first parameter
```go
func Process(ctx context.Context, data []byte) error
```

**2.4.5** Parameter naming matches operation
```go
Create(ctx context.Context, data *CreateParam) (int64, error)  // create doesn't need ID
Update(ctx context.Context, id int64, data *UpdateParam) error // update needs ID
```

**2.4.6** More than 4 parameters - use struct
```go
type CreateUserParams struct {
    Name  string
    Email string
    Phone string
    Role  string
}
func CreateUser(ctx context.Context, params *CreateUserParams) error
```

**2.4.7** Multiple return values of same type must be named
When a function returns multiple values of the same type (except error), use named return values to improve clarity and prevent confusion.
```go
// ❌ Problem - unclear which string is which
func ParseUser(data string) (string, string, error) {
    // returns name and email, but which is which?
}

// ✅ Fix - named return values make it clear
func ParseUser(data string) (name string, email string, err error) {
    // clear what each return value represents
    return "John", "john@example.com", nil
}

// ✅ Also acceptable - different types don't need naming
func GetUserCount() (int, error) {
    // only one non-error return, naming not required
}

// ✅ Single type return doesn't need naming
func GetUserName() (string, error) {
    // only one non-error return, clear purpose
}
```

**2.4.8** Required parameters must consider zero value validity
- If zero value is valid, use pointer type to distinguish "not provided" vs "zero value provided"
- If zero value is invalid, use value type
```go
// ✅ Zero value valid - use pointer
type UpdateUserRequest struct {
    ID     int64   `json:"id" validate:"required"`
    Status *int    `json:"status" validate:"required"` // 0 is valid
    Age    *int    `json:"age" validate:"required"`    // 0 years may be valid
}

// ✅ Zero value invalid - use value type
type CreateUserRequest struct {
    Name   string `json:"name" validate:"required"`    // empty string invalid
    Email  string `json:"email" validate:"required"`   // empty string invalid
    RoleID int64  `json:"role_id" validate:"required"` // 0 invalid (by business rule)
}
```

**2.4.9** Avoid ineffective encapsulation
Don't create ineffective encapsulation, directly calling underlying methods may be more convenient.
- ❌ Don't create ineffective encapsulation, directly calling `db` query is more convenient than calling this method
- ✅ Encapsulation should provide real value
- ❌ Avoid encapsulation just for the sake of encapsulation

**2.4.10** Parameter design should be reasonable
Function parameter design should be reasonable, cannot have logical contradictions.
- ❌ Why does getting account need to pass account list? Parameter design is unreasonable
- ✅ Function parameters should conform to business logic
- ✅ Parameter names and purposes should be consistent

---

### 2.5 Code Quality

**2.5.1** No spelling errors (except whitelist)

**2.5.2** Function length should be moderate - split if too long

**2.5.3** Public functions must have comments
```go
// GetUserByID retrieves user by ID
// Parameters:
//   ctx: context
//   id: user ID
// Returns:
//   *User: user info
//   error: error if any
func GetUserByID(ctx context.Context, id int64) (*User, error)
```

**2.5.4** Enum constants must have Chinese comments and be aligned
```go
const (
    StatusInit     = 0 // 初始化
    StatusPending  = 1 // 待处理
    StatusApproved = 2 // 已通过
)
```

**2.5.5** Inject dependencies via constructor

**2.5.6** Use struct embedding for code reuse

---

## P2 Rules - Suggested

### 3.1 Project Structure

**3.1.1** Package name matches directory name

**3.1.2** Import grouping and sorting
```go
import (
    // Standard library
    "context"
    "fmt"

    // Third-party
    "github.com/pkg/errors"

    // Internal
    "project/internal/model"
)
```

**3.1.3** Business logic in `biz/`, data access in `data/`

**3.1.4** Cloud provider code organized by provider

**3.1.5** Configuration code in `config/`

**3.1.6** Utility code in `pkg/`

**3.1.7** Initialization in `server/server.go`

**3.1.8** Service implementation in `service/`

**3.1.9** Use framework-provided utilities
Should prioritize using utility methods provided by frameworks or libraries, instead of implementing yourself.
- ✅ List already provides `orm.Slice`, should use it
- ✅ Prioritize using standard library and framework-provided functionality
- ❌ Avoid reinventing the wheel

**3.1.10** Don't commit debug code
Debug code and initialization content should not be committed to code repository.
- ❌ Debug code should not be committed
- ❌ Initialization content doesn't need to be committed
- ✅ Keep code repository clean

---

### 3.2 Testing Standards

**3.2.1** Unit tests must verify specific structure, not just err != nil
Unit tests must verify specific business logic, cannot just verify that interface doesn't error.
- ✅ Tests need to verify specific logic, not just that interface doesn't error
- ✅ Tests should verify correctness of business logic
- ✅ Need to verify return values and state changes

```go
// ✅ Correct: Verify specific structure
assert.NoError(t, err)
assert.Equal(t, expectedValue, actualValue)
assert.Equal(t, expectedStatus, result.Status)

// ❌ Incorrect: Only check err != nil
if err != nil {
    t.Fatal(err)
}
// Missing verification of actual business logic
```

**3.2.2** Test file naming: `xxx_test.go`

**3.2.3** Test function naming: `TestXxx`

**3.2.4** Unit tests should be lightweight
Unit tests should be lightweight, directly associated with specific functionality, don't need to start complete application.
- ✅ No `biz_test`, directly associate with specific functionality
- ❌ Non-interface unit tests should not use `application.Run`
- ✅ Unit tests should execute quickly, not depend on external services

**3.2.5** Mock implementation standards
Mock implementations should be placed in independent mock files, completed through interface implementation, not hardcode.
- ✅ `mock` should be placed in independent `mock` files
- ✅ `mock` should be completed through interface implementation, not hardcode
- ✅ Mock implementations should be clear and maintainable

**3.2.6** Interface test location standards
Interface tests should be placed in `internal/test` directory, separated from unit tests.
- ✅ Interface tests should be placed in `internal/test` directory
- ✅ Interface tests and unit tests should be separated
- ✅ Keep test code organization clear

**3.2.7** Unit tests must not start services
Unit tests must not start complete services, should use mock database.
- ❌ Unit tests must not start services, should use mock database
- ✅ Tests should run independently, not depend on external services
- ✅ Use mocks to simulate external dependencies

---

### 3.3 Configuration Management

**3.3.1** Configuration updates should take effect dynamically
```go
func (c *Config) OnConfigChange() error {
    // handle config update
}
```

---

## P1 Rules - Design Philosophies

This section covers classic software design philosophies adapted for Go. These are strongly recommended guidelines that help maintain clean, maintainable, and scalable code.

### 4.1 KISS (Keep It Simple, Stupid) 简单优先原则

The KISS principle emphasizes simplicity in design and implementation. Simple code is easier to understand, test, and maintain.

**4.1.1** 避免不必要的抽象层 (Avoid Unnecessary Abstraction Layers)

只有在存在多个实现或明确需要解耦时才创建接口。不要为单一实现创建接口，这会增加复杂性而不带来价值。

✅ **正确示例 - 直接实现**:
```go
// 简单、直接的实现
func LoadConfig(path string) (*Config, error) {
    data, err := os.ReadFile(path)
    if err != nil {
        return nil, errors.Wrap(err, "failed to read config")
    }
    var config Config
    if err := json.Unmarshal(data, &config); err != nil {
        return nil, errors.Wrap(err, "failed to unmarshal config")
    }
    return &config, nil
}
```

❌ **错误示例 - 不必要的抽象**:
```go
// 不必要的接口 - 只有一个实现
type ConfigLoader interface {
    Load(path string) (*Config, error)
}

type FileConfigLoader struct{}

func (f *FileConfigLoader) Load(path string) (*Config, error) {
    // 唯一的实现，接口没有增加任何价值
    return &Config{}, nil
}

// 过度设计的工厂
type ConfigFactory interface {
    CreateLoader() ConfigLoader
}
```

**原因**: 接口应该在有多个实现或需要解耦时才存在。过早的抽象会增加复杂性而没有好处。

---

**4.1.2** 保持函数简单直接 (Keep Functions Simple and Direct)

函数应该保持简单，通常不超过 50 行。长函数难以理解和测试，应该拆分成更小的、职责单一的函数。

✅ **正确示例 - 简单函数**:
```go
// 简单、清晰的函数
func ValidateUser(user *User) error {
    if user == nil {
        return errors.New("user is nil")
    }
    if user.Name == "" {
        return errors.New("user name is empty")
    }
    if user.Email == "" {
        return errors.New("user email is empty")
    }
    return nil
}

func CreateUser(ctx context.Context, user *User) error {
    if err := ValidateUser(user); err != nil {
        return errors.Wrap(err, "validation failed")
    }
    return saveUser(ctx, user)
}
```

❌ **错误示例 - 过长复杂的函数**:
```go
// 函数过长，包含多个职责
func CreateUser(ctx context.Context, user *User) error {
    // 验证逻辑 (20 行)
    if user == nil { return errors.New("user is nil") }
    if user.Name == "" { return errors.New("name empty") }
    if user.Email == "" { return errors.New("email empty") }
    if !strings.Contains(user.Email, "@") { return errors.New("invalid email") }

    // 权限检查 (15 行)
    if user.Role == "admin" && !ctx.Value("is_admin").(bool) {
        return errors.New("no permission")
    }

    // 数据转换 (20 行)
    data := convertUserData(user)

    // 数据库操作 (15 行)
    tx := db.Begin()
    if err := tx.Create(&data).Error; err != nil {
        tx.Rollback()
        return err
    }

    // 发送邮件 (20 行)
    sendEmail(user.Email, "Welcome")

    // 记录日志 (10 行)
    log.Info("user created")

    tx.Commit()
    return nil
}
```

**原因**: 简单的函数更容易理解、测试和维护。复杂的函数应该拆分成多个小函数，每个函数专注于单一职责。

---

**4.1.3** 避免过度使用 channel 和 goroutine (Avoid Overusing Channels and Goroutines)

并发增加了 goroutine 开销和同步复杂性。对于简单的内存操作，顺序执行通常更快更清晰。只在 I/O 密集型或 CPU 密集型任务中使用并发。

✅ **正确示例 - 简单转换使用顺序执行**:
```go
// 简单的数据转换 - 顺序更清晰
func ProcessUsers(users []*User) []*UserDTO {
    results := make([]*UserDTO, 0, len(users))
    for _, user := range users {
        results = append(results, &UserDTO{
            ID:   user.ID,
            Name: user.Name,
        })
    }
    return results
}
```

❌ **错误示例 - 不必要的并发**:
```go
// 简单转换使用了不必要的 goroutine
func ProcessUsers(users []*User) []*UserDTO {
    ch := make(chan *UserDTO, len(users))

    for _, user := range users {
        go func(u *User) {
            ch <- &UserDTO{ID: u.ID, Name: u.Name}
        }(user)
    }

    results := make([]*UserDTO, 0, len(users))
    for i := 0; i < len(users); i++ {
        results = append(results, <-ch)
    }
    return results
}
```

**原因**: 并发增加了 goroutine 开销和同步复杂性。简单的内存操作顺序执行更快。只在 I/O 密集型或 CPU 密集型任务中使用并发。

---

**4.1.4** 优先使用直接的控制流 (Prefer Direct Control Flow)

使用清晰的 if-else 语句而不是复杂的函数式链或间接跳转。直接的控制流更容易理解和调试。

✅ **正确示例 - 清晰的控制流**:
```go
func ProcessOrder(order *Order) error {
    if order == nil {
        return errors.New("order is nil")
    }

    if order.Status != "pending" {
        return errors.New("order not pending")
    }

    if err := validateOrder(order); err != nil {
        return errors.Wrap(err, "validation failed")
    }

    return saveOrder(order)
}
```

❌ **错误示例 - 复杂的函数链**:
```go
// 过于复杂的函数式链
func ProcessOrder(order *Order) error {
    return Optional(order).
        Filter(func(o *Order) bool { return o.Status == "pending" }).
        Map(func(o *Order) (*Order, error) { return validate(o) }).
        FlatMap(func(o *Order) error { return save(o) }).
        OrElse(errors.New("processing failed"))
}
```

**原因**: 直接的 if-else 控制流更容易理解和调试。复杂的函数链增加了认知负担。

---

**4.1.5** 简单的数据结构优于复杂设计 (Simple Data Structures Over Complex Design)

使用明确的 struct 而不是 `map[string]interface{}`。类型安全的结构更容易维护和重构。

✅ **正确示例 - 使用 struct**:
```go
// 明确的数据结构
type UserConfig struct {
    Name     string
    Email    string
    Age      int
    IsActive bool
}

func LoadUserConfig(data []byte) (*UserConfig, error) {
    var config UserConfig
    if err := json.Unmarshal(data, &config); err != nil {
        return nil, errors.Wrap(err, "unmarshal failed")
    }
    return &config, nil
}
```

❌ **错误示例 - 使用 map[string]interface{}**:
```go
// 使用 map - 失去类型安全
func LoadUserConfig(data []byte) (map[string]interface{}, error) {
    var config map[string]interface{}
    if err := json.Unmarshal(data, &config); err != nil {
        return nil, err
    }

    // 需要类型断言，容易出错
    name := config["name"].(string)
    age := int(config["age"].(float64))  // JSON 数字是 float64

    return config, nil
}
```

**原因**: struct 提供类型安全，编译器可以捕获错误。map[string]interface{} 需要运行时类型断言，容易出错。

---

### 4.2 DRY (Don't Repeat Yourself) 避免重复原则

DRY 原则强调消除代码重复。重复的代码增加维护成本，修改时必须在所有地方同步更新。

**4.2.1** 提取重复的业务逻辑到函数 (Extract Repeated Business Logic)

当同样的逻辑出现 3 次或更多时，应该提取为函数。提取的函数提高了可测试性和一致性。

✅ **正确示例 - 提取验证逻辑**:
```go
// 提取的验证函数
func validateUser(user *User) error {
    if user == nil {
        return errors.New("user is nil")
    }
    if user.Name == "" {
        return errors.New("user name is empty")
    }
    if user.Email == "" {
        return errors.New("user email is empty")
    }
    return nil
}

func CreateUser(ctx context.Context, user *User) error {
    if err := validateUser(user); err != nil {
        return errors.Wrap(err, "validation failed")
    }
    return repo.Create(ctx, user)
}

func UpdateUser(ctx context.Context, user *User) error {
    if err := validateUser(user); err != nil {
        return errors.Wrap(err, "validation failed")
    }
    return repo.Update(ctx, user)
}
```

❌ **错误示例 - 重复的验证逻辑**:
```go
func CreateUser(ctx context.Context, user *User) error {
    // 验证逻辑重复
    if user == nil {
        return errors.New("user is nil")
    }
    if user.Name == "" {
        return errors.New("user name is empty")
    }
    if user.Email == "" {
        return errors.New("user email is empty")
    }
    return repo.Create(ctx, user)
}

func UpdateUser(ctx context.Context, user *User) error {
    // 同样的验证逻辑再次出现
    if user == nil {
        return errors.New("user is nil")
    }
    if user.Name == "" {
        return errors.New("user name is empty")
    }
    if user.Email == "" {
        return errors.New("user email is empty")
    }
    return repo.Update(ctx, user)
}
```

**原因**: 重复的代码增加维护成本。修改必须在所有地方同步。提取的函数提高可测试性和一致性。

---

**4.2.2** 使用常量替代魔法数字和字符串 (Use Constants for Magic Numbers and Strings)

常量提供语义化的名称，支持统一修改，防止拼写错误。

✅ **正确示例 - 使用常量**:
```go
const (
    MaxRetryCount        = 3              // 最大重试次数
    DefaultTimeout       = 30             // 默认超时时间(秒)
    MaxPageSize          = 100            // 最大分页大小
    RoleAdmin     string = "admin"        // 管理员角色
    RoleUser      string = "user"         // 普通用户角色
)

func ListUsers(page, pageSize int) ([]*User, error) {
    if pageSize > MaxPageSize {
        pageSize = MaxPageSize
    }
    // ...
    return users, nil
}

func CheckUserRole(role string) bool {
    return role == RoleAdmin || role == RoleUser
}
```

❌ **错误示例 - 魔法数字和字符串**:
```go
func ListUsers(page, pageSize int) ([]*User, error) {
    if pageSize > 100 {  // 100 是什么意思?
        pageSize = 100
    }
    // ...
    return users, nil
}

func CheckUserRole(role string) bool {
    return role == "admin" || role == "user"  // 硬编码字符串
}

func RetryOperation() error {
    for i := 0; i < 3; i++ {  // 3 是什么意思?
        // ...
    }
    return nil
}
```

**原因**: 常量提供语义化的名称，支持统一修改，防止拼写错误。

---

**4.2.3** 共享数据结构定义 (Share Data Structure Definitions)

使用结构体嵌入来复用字段定义。修改公共字段时只需要编辑一处。

✅ **正确示例 - 使用嵌入**:
```go
// 基础模型，包含公共字段
type BaseModel struct {
    ID         int64     `gorm:"column:id"`
    CreateTime time.Time `gorm:"column:create_time"`
    UpdateTime time.Time `gorm:"column:update_time"`
    Creator    string    `gorm:"column:creator"`
    Modifier   string    `gorm:"column:modifier"`
}

// User 嵌入 BaseModel
type User struct {
    BaseModel
    Name  string `gorm:"column:name"`
    Email string `gorm:"column:email"`
}

// Product 嵌入 BaseModel
type Product struct {
    BaseModel
    Name  string  `gorm:"column:name"`
    Price float64 `gorm:"column:price"`
}
```

❌ **错误示例 - 重复字段定义**:
```go
// 每个结构体都重复定义相同的字段
type User struct {
    ID         int64     `gorm:"column:id"`        // 重复
    CreateTime time.Time `gorm:"column:create_time"` // 重复
    UpdateTime time.Time `gorm:"column:update_time"` // 重复
    Creator    string    `gorm:"column:creator"`     // 重复
    Modifier   string    `gorm:"column:modifier"`    // 重复
    Name       string    `gorm:"column:name"`
    Email      string    `gorm:"column:email"`
}

type Product struct {
    ID         int64     `gorm:"column:id"`        // 重复
    CreateTime time.Time `gorm:"column:create_time"` // 重复
    UpdateTime time.Time `gorm:"column:update_time"` // 重复
    Creator    string    `gorm:"column:creator"`     // 重复
    Modifier   string    `gorm:"column:modifier"`    // 重复
    Name       string    `gorm:"column:name"`
    Price      float64   `gorm:"column:price"`
}
```

**原因**: 减少重复，集中管理公共字段，修改公共字段时只需要编辑一处。

---

**4.2.4** 避免重复的错误处理模式 (Avoid Repeated Error Handling Patterns)

提取公共的错误处理逻辑，保持代码 DRY。

✅ **正确示例 - 提取错误处理**:
```go
// 提取的错误处理辅助函数
func handleDBError(err error, operation string) error {
    if err == nil {
        return nil
    }
    if errors.Is(err, gorm.ErrRecordNotFound) {
        return errors.Wrapf(err, "%s: record not found", operation)
    }
    return errors.Wrapf(err, "%s failed", operation)
}

func GetUser(ctx context.Context, id int64) (*User, error) {
    var user User
    err := db.Where("id = ?", id).First(&user).Error
    return &user, handleDBError(err, "get user")
}

func GetProduct(ctx context.Context, id int64) (*Product, error) {
    var product Product
    err := db.Where("id = ?", id).First(&product).Error
    return &product, handleDBError(err, "get product")
}
```

❌ **错误示例 - 重复的错误处理**:
```go
func GetUser(ctx context.Context, id int64) (*User, error) {
    var user User
    err := db.Where("id = ?", id).First(&user).Error
    if err != nil {
        if errors.Is(err, gorm.ErrRecordNotFound) {
            return nil, errors.Wrap(err, "get user: record not found")
        }
        return nil, errors.Wrap(err, "get user failed")
    }
    return &user, nil
}

func GetProduct(ctx context.Context, id int64) (*Product, error) {
    var product Product
    err := db.Where("id = ?", id).First(&product).Error
    // 相同的错误处理模式重复出现
    if err != nil {
        if errors.Is(err, gorm.ErrRecordNotFound) {
            return nil, errors.Wrap(err, "get product: record not found")
        }
        return nil, errors.Wrap(err, "get product failed")
    }
    return &product, nil
}
```

**原因**: 提取公共的错误处理逻辑，保持一致性，减少重复代码。

---

**4.2.5** 复用已有的工具函数 (Reuse Existing Utility Functions)

在实现新功能前，先检查是否已有可用的工具函数。复用现有代码而不是重新实现。

✅ **正确示例 - 复用现有工具**:
```go
// 使用已有的转换函数
import "project/pkg/convert"

func CreateUserDTO(user *User) *UserDTO {
    return &UserDTO{
        ID:   user.ID,
        Name: user.Name,
        Time: convert.TimeToString(user.CreateTime),  // 复用已有工具
    }
}
```

❌ **错误示例 - 重新实现已有功能**:
```go
func CreateUserDTO(user *User) *UserDTO {
    // 重新实现时间转换，但项目中已有 convert.TimeToString
    timeStr := user.CreateTime.Format("2006-01-02 15:04:05")

    return &UserDTO{
        ID:   user.ID,
        Name: user.Name,
        Time: timeStr,
    }
}
```

**原因**: 复用现有工具保持代码一致性，避免重复实现相同功能。

---

### 4.3 YAGNI (You Aren't Gonna Need It) 不做过度开发原则

YAGNI 原则强调只实现当前需要的功能，不要为未来可能的需求编写代码。未来的需求可能永远不会出现或完全改变。

**4.3.1** 不实现未来可能需要的功能 (Don't Implement Future Features)

只实现当前需求。未来的需求可能永远不会实现或完全改变。提前实现会增加维护负担。

✅ **正确示例 - 只实现当前需求**:
```go
// 只实现当前需求：通过 ID 获取用户
type UserRepository struct {
    db *gorm.DB
}

func (r *UserRepository) GetByID(ctx context.Context, id int64) (*User, error) {
    var user User
    err := r.db.Where("id = ?", id).Take(&user).Error
    if err != nil {
        return nil, errors.Wrap(err, "failed to get user")
    }
    return &user, nil
}
```

❌ **错误示例 - 实现"未来可能"的功能**:
```go
type UserRepository struct {
    db *gorm.DB
}

func (r *UserRepository) GetByID(ctx context.Context, id int64) (*User, error) {
    return &User{}, nil  // 当前需求
}

// 以下方法没有调用者 - "可能以后需要"
func (r *UserRepository) GetByEmail(ctx context.Context, email string) (*User, error) {
    return &User{}, nil  // 没有当前需求
}

func (r *UserRepository) GetByPhone(ctx context.Context, phone string) (*User, error) {
    return &User{}, nil  // 没有当前需求
}

func (r *UserRepository) SearchByKeyword(ctx context.Context, keyword string) ([]*User, error) {
    return nil, nil  // 没有当前需求
}
```

**原因**: 未来的需求可能永远不会实现或完全改变。提前实现会增加维护负担。需要时再添加功能。

---

**4.3.2** 避免过度参数化 (Avoid Over-Parameterization)

不要添加"可能有用"的参数。参数应该解决实际存在的问题。

✅ **正确示例 - 只有必要的参数**:
```go
// 只接受当前需要的参数
func CreateUser(ctx context.Context, name, email string) error {
    user := &User{
        Name:  name,
        Email: email,
    }
    return saveUser(ctx, user)
}
```

❌ **错误示例 - 过度参数化**:
```go
// 添加了"可能有用"的参数
func CreateUser(
    ctx context.Context,
    name, email string,
    enableCache bool,        // "可能需要控制缓存"
    auditLog bool,           // "可能需要审计日志"
    notifyAdmin bool,        // "可能需要通知管理员"
    customMetadata map[string]interface{},  // "可能需要自定义元数据"
) error {
    // 实际上这些参数都没有被使用
    user := &User{Name: name, Email: email}
    return saveUser(ctx, user)
}
```

**原因**: "可能有用"的参数增加了接口复杂性。应该在真正需要时才添加参数。

---

**4.3.3** 不预先设计扩展点 (Don't Pre-Design Extension Points)

不要为"未来扩展"创建接口。当真正需要多个实现时再引入接口。

✅ **正确示例 - 直接实现**:
```go
// 当前只需要一种通知方式
type Notifier struct {
    emailClient *EmailClient
}

func (n *Notifier) Notify(ctx context.Context, user *User, message string) error {
    return n.emailClient.Send(user.Email, message)
}
```

❌ **错误示例 - 预先设计扩展点**:
```go
// 创建接口"以便将来扩展"
type NotificationChannel interface {
    Send(ctx context.Context, recipient string, message string) error
}

type EmailChannel struct{}
func (e *EmailChannel) Send(ctx context.Context, recipient string, message string) error {
    return nil
}

// 创建策略模式"以便将来添加更多渠道"
type NotificationStrategy struct {
    channels map[string]NotificationChannel
}

func (s *NotificationStrategy) RegisterChannel(name string, channel NotificationChannel) {
    // 实际上永远只用 email
}

// 工厂模式"以便将来扩展"
type ChannelFactory interface {
    CreateChannel(channelType string) NotificationChannel
}
```

**原因**: 当只有一个实现时，接口增加了不必要的复杂性。真正需要多个实现时再引入抽象。

---

**4.3.4** 删除未使用的代码 (Delete Unused Code)

未使用的代码增加维护负担和困惑。Git 历史会保留旧代码。应该立即删除。

✅ **正确示例 - 只保留使用的代码**:
```go
type UserService struct {
    repo UserRepository
}

// CreateUser - 有调用者
func (s *UserService) CreateUser(ctx context.Context, user *User) error {
    return s.repo.Create(ctx, user)
}

// GetUser - 有调用者
func (s *UserService) GetUser(ctx context.Context, id int64) (*User, error) {
    return s.repo.GetByID(ctx, id)
}
```

❌ **错误示例 - 保留未使用的代码**:
```go
type UserService struct {
    repo UserRepository
}

func (s *UserService) CreateUser(ctx context.Context, user *User) error {
    return s.repo.Create(ctx, user)
}

func (s *UserService) GetUser(ctx context.Context, id int64) (*User, error) {
    return s.repo.GetByID(ctx, id)
}

// 未使用的方法 - 应该删除
func (s *UserService) UpdateUser(ctx context.Context, user *User) error {
    return s.repo.Update(ctx, user)  // 没有调用者
}

func (s *UserService) DeleteUser(ctx context.Context, id int64) error {
    return s.repo.Delete(ctx, id)  // 没有调用者
}

// 注释掉的旧实现 - 应该删除
// func (s *UserService) OldCreateUser(ctx context.Context, user *User) error {
//     // 旧逻辑...
//     return nil
// }
```

**原因**: 未使用的代码增加维护负担和困惑。Git 历史会保留旧代码。应该立即删除。

---

**4.3.5** 避免不必要的配置选项 (Avoid Unnecessary Configuration Options)

配置应该解决实际问题。不要添加"可能有用"的配置。

✅ **正确示例 - 必要的配置**:
```go
type ServerConfig struct {
    Port    int    // 必须可配置
    Host    string // 必须可配置
    Timeout int    // 实际需要调整
}

func NewServer(config *ServerConfig) *Server {
    return &Server{
        port:    config.Port,
        host:    config.Host,
        timeout: time.Duration(config.Timeout) * time.Second,
    }
}
```

❌ **错误示例 - 过度配置**:
```go
type ServerConfig struct {
    Port                int
    Host                string
    Timeout             int
    EnableDebugMode     bool              // "可能需要"
    MaxConnectionsPerIP int               // "可能需要限制"
    EnableMetrics       bool              // "可能需要监控"
    MetricsPort         int               // "如果启用监控"
    EnableRateLimit     bool              // "可能需要"
    RateLimitPerSecond  int               // "如果启用限流"
    CustomHeader        map[string]string // "可能需要自定义"
    EnableCompression   bool              // "可能提高性能"
}

// 实际上大部分配置都使用默认值，从未改变
```

**原因**: 配置应该解决实际问题。过多的配置增加了复杂性，并且很多配置永远不会被修改。

---

### 4.4 SOLID Principles SOLID 设计原则

SOLID 是五个面向对象设计原则的缩写。虽然 Go 不是传统的面向对象语言，但这些原则仍然适用。

**4.4.1** 单一职责原则 (Single Responsibility Principle - SRP)

每个函数/结构体应该只有一个改变的理由。职责分离使每个组件更容易理解、测试和独立修改。

✅ **正确示例 - 职责分离**:
```go
// UserValidator - 只负责验证
type UserValidator struct{}

func (v *UserValidator) Validate(user *User) error {
    if user.Name == "" {
        return errors.New("name is required")
    }
    return nil
}

// UserRepository - 只负责数据访问
type UserRepository struct {
    db *gorm.DB
}

func (r *UserRepository) Create(ctx context.Context, user *User) error {
    return r.db.Create(user).Error
}

// UserService - 只负责业务逻辑
type UserService struct {
    validator *UserValidator
    repo      *UserRepository
}

func (s *UserService) CreateUser(ctx context.Context, user *User) error {
    if err := s.validator.Validate(user); err != nil {
        return errors.Wrap(err, "validation failed")
    }
    return s.repo.Create(ctx, user)
}
```

❌ **错误示例 - 多重职责**:
```go
// UserService 承担了过多职责
type UserService struct {
    db *gorm.DB
}

func (s *UserService) CreateUser(ctx context.Context, user *User) error {
    // 职责 1: 验证
    if user.Name == "" {
        return errors.New("name is required")
    }

    // 职责 2: 发送邮件
    emailContent := fmt.Sprintf("Welcome %s!", user.Name)
    sendEmail(user.Email, emailContent)

    // 职责 3: 数据库操作
    s.db.Create(user)

    // 职责 4: 日志记录
    log.Info(ctx, "user created", log.Int64("user_id", user.ID))

    // 职责 5: 缓存更新
    cache.Set(fmt.Sprintf("user:%d", user.ID), user)

    return nil
}
```

**原因**: 职责分离使每个组件更容易理解、测试和独立修改。

---

**4.4.2** 开放封闭原则 (Open-Closed Principle - OCP)

软件实体应该对扩展开放，对修改封闭。通过接口扩展功能，而不是修改现有代码。

✅ **正确示例 - 通过接口扩展**:
```go
// 定义接口
type PaymentMethod interface {
    Pay(ctx context.Context, amount float64) error
}

// 已有实现
type CreditCardPayment struct{}
func (c *CreditCardPayment) Pay(ctx context.Context, amount float64) error {
    return nil
}

// 新增实现 - 无需修改现有代码
type AlipayPayment struct{}
func (a *AlipayPayment) Pay(ctx context.Context, amount float64) error {
    return nil
}

// 支付服务 - 无需修改
type PaymentService struct {
    method PaymentMethod
}

func (s *PaymentService) ProcessPayment(ctx context.Context, amount float64) error {
    return s.method.Pay(ctx, amount)
}
```

❌ **错误示例 - 通过修改扩展**:
```go
type PaymentService struct{}

func (s *PaymentService) ProcessPayment(ctx context.Context, paymentType string, amount float64) error {
    // 每增加一种支付方式都要修改这个函数
    switch paymentType {
    case "credit_card":
        return s.processCreditCard(amount)
    case "alipay":  // 新增需要修改
        return s.processAlipay(amount)
    case "wechat":  // 新增需要修改
        return s.processWechat(amount)
    default:
        return errors.New("unsupported payment type")
    }
}
```

**原因**: 通过接口扩展避免了修改现有代码，减少了引入 bug 的风险。

---

**4.4.3** 接口隔离原则 (Interface Segregation Principle - ISP)

客户端不应该被迫依赖它不使用的方法。使用小而专注的接口。

✅ **正确示例 - 小接口**:
```go
// 小的、专注的接口
type UserReader interface {
    GetUser(ctx context.Context, id int64) (*User, error)
}

type UserWriter interface {
    CreateUser(ctx context.Context, user *User) error
    UpdateUser(ctx context.Context, user *User) error
}

type UserDeleter interface {
    DeleteUser(ctx context.Context, id int64) error
}

// 只读服务只依赖 UserReader
type UserQueryService struct {
    reader UserReader
}

func (s *UserQueryService) GetUserInfo(ctx context.Context, id int64) (*User, error) {
    return s.reader.GetUser(ctx, id)
}
```

❌ **错误示例 - 大接口**:
```go
// 臃肿的接口包含所有方法
type UserRepository interface {
    GetUser(ctx context.Context, id int64) (*User, error)
    GetUserByEmail(ctx context.Context, email string) (*User, error)
    ListUsers(ctx context.Context, offset, limit int) ([]*User, error)
    CreateUser(ctx context.Context, user *User) error
    UpdateUser(ctx context.Context, user *User) error
    DeleteUser(ctx context.Context, id int64) error
    BatchCreate(ctx context.Context, users []*User) error
    BatchDelete(ctx context.Context, ids []int64) error
    CountUsers(ctx context.Context) (int64, error)
}

// 被迫依赖整个接口，但只使用一个方法
type UserQueryService struct {
    repo UserRepository  // 只使用 GetUser
}
```

**原因**: 大接口难以 mock 和测试。客户端被迫依赖不使用的方法。Go 的接口组合很强大 - 使用它。

---

**4.4.4** 依赖反转原则 (Dependency Inversion Principle - DIP)

高层模块不应该依赖低层模块。两者都应该依赖抽象（接口）。

✅ **正确示例 - 依赖接口**:
```go
// 定义接口（抽象）
type UserRepository interface {
    GetByID(ctx context.Context, id int64) (*User, error)
}

// 高层模块依赖接口
type UserService struct {
    repo UserRepository  // 依赖接口，不是具体实现
}

func NewUserService(repo UserRepository) *UserService {
    return &UserService{repo: repo}
}

// 低层模块实现接口
type MySQLUserRepository struct {
    db *gorm.DB
}

func (r *MySQLUserRepository) GetByID(ctx context.Context, id int64) (*User, error) {
    var user User
    err := r.db.Where("id = ?", id).Take(&user).Error
    return &user, err
}
```

❌ **错误示例 - 依赖具体实现**:
```go
// 低层模块（具体实现）
type MySQLUserRepository struct {
    db *gorm.DB
}

func (r *MySQLUserRepository) GetByID(ctx context.Context, id int64) (*User, error) {
    return &User{}, nil
}

// 高层模块直接依赖低层模块
type UserService struct {
    repo *MySQLUserRepository  // 直接依赖具体实现
}

func NewUserService(db *gorm.DB) *UserService {
    return &UserService{
        repo: &MySQLUserRepository{db: db},  // 直接创建具体实现
    }
}
```

**原因**: 依赖接口使得测试更容易（可以注入 mock），也允许更换实现而不影响高层模块。

---

**4.4.5** 里氏替换原则 (Liskov Substitution Principle - LSP)

子类型必须能够替换其基类型。实现必须遵守接口约定。

✅ **正确示例 - 遵守接口约定**:
```go
type Storage interface {
    Save(ctx context.Context, key string, data []byte) error
}

// FileStorage 正确实现了 Storage
type FileStorage struct {
    basePath string
}

func (f *FileStorage) Save(ctx context.Context, key string, data []byte) error {
    path := filepath.Join(f.basePath, key)
    return os.WriteFile(path, data, 0644)  // 正确实现
}

// MemoryStorage 也正确实现了 Storage
type MemoryStorage struct {
    data map[string][]byte
}

func (m *MemoryStorage) Save(ctx context.Context, key string, data []byte) error {
    m.data[key] = data  // 正确实现
    return nil
}

// 两个实现都可以互换使用
func SaveUserData(storage Storage, user *User) error {
    data, _ := json.Marshal(user)
    return storage.Save(context.Background(), "user", data)
}
```

❌ **错误示例 - 违反接口约定**:
```go
type Storage interface {
    Save(ctx context.Context, key string, data []byte) error
}

// ReadOnlyStorage 违反了接口约定
type ReadOnlyStorage struct{}

func (r *ReadOnlyStorage) Save(ctx context.Context, key string, data []byte) error {
    // 违反约定：声称实现 Save 但实际不支持
    return errors.New("not supported")  // 错误！
}

// LimitedStorage 违反了接口约定
type LimitedStorage struct{}

func (l *LimitedStorage) Save(ctx context.Context, key string, data []byte) error {
    if len(data) > 100 {
        // 违反约定：添加了接口未声明的限制
        return errors.New("data too large")
    }
    return nil
}
```

**原因**: 实现必须遵守接口约定。违反约定会导致使用者的代码出现意外行为。

---

### 4.5 LoD (Law of Demeter) 迪米特法则

迪米特法则（最少知识原则）强调减少对象间的直接依赖。对象应该只与直接的朋友交流。

**4.5.1** 避免链式调用 (Avoid Method Chaining on Objects)

链式调用暴露了内部实现。对内部结构的改变会破坏所有客户端。难以处理 nil 检查和错误。

✅ **正确示例 - 提供专门方法**:
```go
type User struct {
    profile *Profile
}

type Profile struct {
    address *Address
}

type Address struct {
    city string
}

// 提供专门方法隐藏内部结构
func (u *User) GetCity() (string, error) {
    if u.profile == nil {
        return "", errors.New("profile is nil")
    }
    if u.profile.address == nil {
        return "", errors.New("address is nil")
    }
    return u.profile.address.city, nil
}

// 客户端代码简单
func PrintUserCity(user *User) {
    city, err := user.GetCity()
    if err != nil {
        log.Error(ctx, "failed to get city", log.ErrorField(err))
        return
    }
    fmt.Println(city)
}
```

❌ **错误示例 - 链式调用**:
```go
type User struct {
    Profile *Profile  // 导出
}

type Profile struct {
    Address *Address  // 导出
}

type Address struct {
    City string  // 导出
}

// 客户端直接访问深层结构
func PrintUserCity(user *User) {
    // 链式调用暴露内部实现
    city := user.Profile.Address.City  // 任何 nil 都会 panic

    fmt.Println(city)

    // 即使加了检查，也暴露了太多细节
    if user.Profile != nil && user.Profile.Address != nil {
        fmt.Println(user.Profile.Address.City)
    }
}
```

**原因**: 链式调用暴露内部实现。对内部结构的改变会破坏所有客户端。难以处理 nil 检查和错误。

---

**4.5.2** 不访问返回对象的内部 (Don't Access Internals of Returned Objects)

不要访问通过方法返回的对象的内部结构。提供专门的访问方法。

✅ **正确示例 - 提供访问方法**:
```go
type Order struct {
    items []*OrderItem
}

type OrderItem struct {
    product *Product
    price   float64
}

// 提供专门的访问方法
func (o *Order) GetTotalPrice() float64 {
    var total float64
    for _, item := range o.items {
        total += item.price
    }
    return total
}

func (o *Order) GetProductNames() []string {
    names := make([]string, 0, len(o.items))
    for _, item := range o.items {
        if item.product != nil {
            names = append(names, item.product.Name)
        }
    }
    return names
}

// 客户端使用访问方法
func ProcessOrder(order *Order) {
    total := order.GetTotalPrice()
    products := order.GetProductNames()
    fmt.Printf("Total: %.2f, Products: %v\n", total, products)
}
```

❌ **错误示例 - 访问返回对象的内部**:
```go
type Order struct {
    Items []*OrderItem  // 导出
}

type OrderItem struct {
    Product *Product  // 导出
    Price   float64   // 导出
}

// 客户端直接访问内部结构
func ProcessOrder(order *Order) {
    var total float64
    for _, item := range order.Items {
        total += item.Price  // 访问返回对象的内部
    }

    for _, item := range order.Items {
        if item.Product != nil {
            fmt.Println(item.Product.Name)  // 深层访问
        }
    }
}
```

**原因**: 访问内部结构增加了耦合。提供专门方法可以隐藏实现细节，便于后续修改。

---

**4.5.3** 限制函数的依赖范围 (Limit Function Dependency Scope)

函数只应该调用以下对象的方法：自身、参数、自己创建的对象、字段。

✅ **正确示例 - 限制依赖**:
```go
type OrderService struct {
    validator *OrderValidator
    repo      *OrderRepository
}

func (s *OrderService) CreateOrder(ctx context.Context, order *Order) error {
    // 1. 调用字段的方法
    if err := s.validator.Validate(order); err != nil {
        return errors.Wrap(err, "validation failed")
    }

    // 2. 调用参数的方法
    order.CalculateTotal()

    // 3. 创建并使用本地对象
    notifier := NewOrderNotifier()
    notifier.Notify(order)

    // 4. 调用字段的方法
    return s.repo.Create(ctx, order)
}
```

❌ **错误示例 - 过度依赖**:
```go
type OrderService struct {
    userRepo *UserRepository
}

func (s *OrderService) CreateOrder(ctx context.Context, order *Order) error {
    // 错误：通过多层调用访问远程对象
    user, _ := s.userRepo.GetByID(ctx, order.UserID)
    address := user.GetProfile().GetAddress()  // 多层链式调用
    city := address.GetCity()                 // 依赖太深

    // 错误：访问全局对象
    emailService := GlobalEmailService
    emailService.Send(user.Email, "Order created")

    return nil
}
```

**原因**: 限制依赖范围减少了模块间的耦合，使代码更容易测试和维护。

---

**4.5.4** 使用依赖注入而非直接创建 (Use Dependency Injection)

依赖注入使得测试更容易（可以注入 mock），使依赖关系明确，允许替换实现。

✅ **正确示例 - 依赖注入**:
```go
// 通过构造函数注入依赖
type UserService struct {
    repo   UserRepository
    cache  Cache
    logger Logger
}

func NewUserService(repo UserRepository, cache Cache, logger Logger) *UserService {
    return &UserService{
        repo:   repo,
        cache:  cache,
        logger: logger,
    }
}

func (s *UserService) GetUser(ctx context.Context, id int64) (*User, error) {
    user, err := s.repo.GetByID(ctx, id)
    if err != nil {
        s.logger.Error(ctx, "failed to get user", log.ErrorField(err))
        return nil, err
    }
    s.cache.Set(fmt.Sprintf("user:%d", id), user)
    return user, nil
}
```

❌ **错误示例 - 内部创建依赖**:
```go
type UserService struct {
    db *gorm.DB
}

func (s *UserService) GetUser(ctx context.Context, id int64) (*User, error) {
    // 在内部创建依赖 - 难以测试
    cache := redis.NewClient(&redis.Options{
        Addr: "localhost:6379",
    })

    logger := zap.NewProduction()

    repo := &UserRepository{db: s.db}

    user, err := repo.GetByID(ctx, id)
    if err != nil {
        logger.Error("failed to get user", zap.Error(err))
        return nil, err
    }

    cache.Set(ctx, fmt.Sprintf("user:%d", id), user, 0)
    return user, nil
}
```

**原因**: 依赖注入使得测试更容易（可以注入 mock），使依赖关系明确，允许替换实现。

---

**4.5.5** 减少对象间的直接耦合 (Reduce Direct Coupling Between Objects)

使用接口来隔离模块。通过接口通信而不是直接依赖具体实现。

✅ **正确示例 - 通过接口解耦**:
```go
// 定义接口
type EmailSender interface {
    Send(to, subject, body string) error
}

type UserNotifier interface {
    NotifyUser(userID int64, message string) error
}

// 服务依赖接口，不是具体实现
type OrderService struct {
    emailSender  EmailSender
    userNotifier UserNotifier
}

func (s *OrderService) ProcessOrder(order *Order) error {
    // 通过接口调用，不知道具体实现
    s.emailSender.Send(order.Email, "Order Confirmed", "...")
    s.userNotifier.NotifyUser(order.UserID, "Order processed")
    return nil
}
```

❌ **错误示例 - 直接耦合**:
```go
type OrderService struct {
    // 直接依赖具体实现
    smtpClient   *SMTPClient
    pushService  *PushNotificationService
    smsGateway   *TwilioSMSGateway
}

func (s *OrderService) ProcessOrder(order *Order) error {
    // 紧密耦合到具体实现
    s.smtpClient.ConnectAndSend(order.Email, "subject", "body")
    s.pushService.SendPushNotification(order.UserID, "message")
    s.smsGateway.SendSMS(order.Phone, "sms content")
    return nil
}
```

**原因**: 通过接口通信减少了耦合，使得模块可以独立演化，更容易测试和替换实现。

---

### 4.6 Composition Over Inheritance 组合优于继承

Go 没有类继承，但提供了结构体嵌入。这个原则强调使用组合和接口来实现代码复用。

**4.6.1** 使用嵌入(embedding)实现代码复用 (Use Embedding for Code Reuse)

减少重复，集中管理公共字段，修改公共字段时只需要编辑一处。

✅ **正确示例 - 使用嵌入**:
```go
// 基础模型，包含公共字段
type BaseModel struct {
    ID         int64     `gorm:"column:id"`
    CreateTime time.Time `gorm:"column:create_time"`
    UpdateTime time.Time `gorm:"column:update_time"`
    Creator    string    `gorm:"column:creator"`
    Modifier   string    `gorm:"column:modifier"`
}

// User 嵌入 BaseModel
type User struct {
    BaseModel
    Name  string `gorm:"column:name"`
    Email string `gorm:"column:email"`
}

// Product 嵌入 BaseModel
type Product struct {
    BaseModel
    Name  string  `gorm:"column:name"`
    Price float64 `gorm:"column:price"`
}

// 可以直接访问嵌入的字段
func PrintUser(user *User) {
    fmt.Println(user.ID)         // 来自 BaseModel
    fmt.Println(user.CreateTime) // 来自 BaseModel
    fmt.Println(user.Name)       // 来自 User
}
```

❌ **错误示例 - 重复字段**:
```go
// 每个结构体都重复字段
type User struct {
    ID         int64     `gorm:"column:id"`        // 重复
    CreateTime time.Time `gorm:"column:create_time"` // 重复
    UpdateTime time.Time `gorm:"column:update_time"` // 重复
    Creator    string    `gorm:"column:creator"`     // 重复
    Modifier   string    `gorm:"column:modifier"`    // 重复
    Name       string    `gorm:"column:name"`
    Email      string    `gorm:"column:email"`
}

type Product struct {
    ID         int64     `gorm:"column:id"`        // 重复
    CreateTime time.Time `gorm:"column:create_time"` // 重复
    UpdateTime time.Time `gorm:"column:update_time"` // 重复
    Creator    string    `gorm:"column:creator"`     // 重复
    Modifier   string    `gorm:"column:modifier"`    // 重复
    Name       string    `gorm:"column:name"`
    Price      float64   `gorm:"column:price"`
}
```

**原因**: 减少重复，集中管理公共字段，修改公共字段时只需要编辑一处。

---

**4.6.2** 通过接口组合实现多态 (Use Interface Composition for Polymorphism)

小接口灵活可组合。避免实现不必要的方法。符合接口隔离原则。Go 的接口组合很强大。

✅ **正确示例 - 接口组合**:
```go
// 小接口定义
type Reader interface {
    Read(ctx context.Context, id int64) ([]byte, error)
}

type Writer interface {
    Write(ctx context.Context, id int64, data []byte) error
}

type Closer interface {
    Close() error
}

// 组合接口
type ReadWriter interface {
    Reader
    Writer
}

type ReadWriteCloser interface {
    Reader
    Writer
    Closer
}

// 按需实现
type FileStorage struct {
    path string
}

func (f *FileStorage) Read(ctx context.Context, id int64) ([]byte, error) {
    return os.ReadFile(f.path)
}

func (f *FileStorage) Write(ctx context.Context, id int64, data []byte) error {
    return os.WriteFile(f.path, data, 0644)
}

func (f *FileStorage) Close() error {
    return nil
}

// 使用合适的接口
func ProcessReadOnly(r Reader) {
    // 只需要读能力
}

func ProcessReadWrite(rw ReadWriter) {
    // 需要读写能力
}
```

❌ **错误示例 - 大接口**:
```go
// 臃肿的接口包含所有方法
type Storage interface {
    Read(ctx context.Context, id int64) ([]byte, error)
    Write(ctx context.Context, id int64, data []byte) error
    Delete(ctx context.Context, id int64) error
    List(ctx context.Context) ([]int64, error)
    Close() error
    Flush() error
    Reset() error
}

// 强制所有实现都实现所有方法
type ReadOnlyStorage struct{}

func (r *ReadOnlyStorage) Read(ctx context.Context, id int64) ([]byte, error) {
    return nil, nil
}

// 不应该存在的方法必须返回错误
func (r *ReadOnlyStorage) Write(ctx context.Context, id int64, data []byte) error {
    return errors.New("not supported")
}

func (r *ReadOnlyStorage) Delete(ctx context.Context, id int64) error {
    return errors.New("not supported")
}
// ... 更多不必要的方法
```

**原因**: 小接口灵活可组合。避免实现不必要的方法。符合接口隔离原则。Go 的接口组合很强大。

---

**4.6.3** 优先组合而非扩展 (Prefer Composition Over Extension)

持有对象作为字段而不是嵌入。组合提供了更明确的关系和更好的封装。

✅ **正确示例 - 使用组合**:
```go
// 组合：持有对象作为字段
type OrderService struct {
    validator    *OrderValidator    // 组合
    priceCalc    *PriceCalculator   // 组合
    notification *NotificationService // 组合
}

func (s *OrderService) CreateOrder(ctx context.Context, order *Order) error {
    // 明确地调用组合对象的方法
    if err := s.validator.Validate(order); err != nil {
        return err
    }

    total := s.priceCalc.Calculate(order.Items)
    order.Total = total

    s.notification.Notify(order)

    return nil
}
```

❌ **错误示例 - 过度使用嵌入**:
```go
// 嵌入所有依赖
type OrderService struct {
    OrderValidator      // 嵌入
    PriceCalculator     // 嵌入
    NotificationService // 嵌入
}

func (s *OrderService) CreateOrder(ctx context.Context, order *Order) error {
    // 不清楚方法来自哪里
    if err := s.Validate(order); err != nil {  // 来自 OrderValidator?
        return err
    }

    total := s.Calculate(order.Items)  // 来自 PriceCalculator?
    order.Total = total

    s.Notify(order)  // 来自 NotificationService?

    return nil
}
```

**原因**: 持有对象作为字段而不是嵌入。组合提供了更明确的关系和更好的封装。

---

**4.6.4** 避免深层嵌入层次 (Avoid Deep Embedding Hierarchy)

最多 2 层嵌入。深层嵌入会导致方法来源不清晰，增加复杂性。

✅ **正确示例 - 浅层嵌入**:
```go
// 层次 1: 基础模型
type BaseModel struct {
    ID         int64
    CreateTime time.Time
}

// 层次 2: 业务模型（最多 2 层）
type User struct {
    BaseModel  // 嵌入基础模型
    Name  string
    Email string
}

// 清晰：只有 2 层
func (u *User) GetID() int64 {
    return u.ID  // 来自 BaseModel
}
```

❌ **错误示例 - 深层嵌入**:
```go
// 层次 1
type Entity struct {
    ID int64
}

// 层次 2
type TimestampedEntity struct {
    Entity
    CreateTime time.Time
}

// 层次 3
type AuditedEntity struct {
    TimestampedEntity
    Creator string
}

// 层次 4 - 太深了！
type User struct {
    AuditedEntity
    Name string
}

// 不清楚 ID 来自哪里
func (u *User) GetID() int64 {
    return u.ID  // 来自 Entity? TimestampedEntity? AuditedEntity?
}
```

**原因**: 最多 2 层嵌入。深层嵌入会导致方法来源不清晰，增加复杂性。

---

**4.6.5** 小接口 + 组合 > 大接口 (Small Interfaces + Composition > Large Interfaces)

实现多个小接口而不是一个大接口。这提供了更大的灵活性和更清晰的职责。

✅ **正确示例 - 实现多个小接口**:
```go
// 定义小接口
type Validator interface {
    Validate() error
}

type Persister interface {
    Save(ctx context.Context) error
}

type Notifier interface {
    Notify(message string) error
}

// 实现多个小接口
type Order struct {
    ID    int64
    Items []OrderItem
}

func (o *Order) Validate() error {
    if len(o.Items) == 0 {
        return errors.New("no items")
    }
    return nil
}

func (o *Order) Save(ctx context.Context) error {
    // 保存逻辑
    return nil
}

func (o *Order) Notify(message string) error {
    // 通知逻辑
    return nil
}

// 灵活使用
func ProcessValidatable(v Validator) error {
    return v.Validate()
}

func ProcessPersistable(p Persister) error {
    return p.Save(context.Background())
}
```

❌ **错误示例 - 大接口**:
```go
// 大的单一接口
type Entity interface {
    Validate() error
    Save(ctx context.Context) error
    Delete(ctx context.Context) error
    Notify(message string) error
    Serialize() ([]byte, error)
    Deserialize(data []byte) error
    GetID() int64
    SetID(id int64)
}

// 强制实现所有方法
type Order struct {
    ID int64
}

// 必须实现所有方法，即使不需要
func (o *Order) Validate() error { return nil }
func (o *Order) Save(ctx context.Context) error { return nil }
func (o *Order) Delete(ctx context.Context) error { return nil }
func (o *Order) Notify(message string) error { return nil }
func (o *Order) Serialize() ([]byte, error) { return nil, nil }
func (o *Order) Deserialize(data []byte) error { return nil }
func (o *Order) GetID() int64 { return o.ID }
func (o *Order) SetID(id int64) { o.ID = id }
```

**原因**: 实现多个小接口提供了更大的灵活性。清晰的职责划分。Go 的隐式接口实现很强大。

---

### 4.7 Less is Exponentially More 少即是多

Go 的核心哲学：少即是多。通过限制语言特性，Go 实现了更强大的表达力和可维护性。

**4.7.1** 避免使用反射 (Avoid Reflection)

反射破坏类型安全，降低性能，增加复杂性。只在绝对必要时使用（如序列化框架）。

✅ **正确示例 - 使用类型断言**:
```go
// 明确的类型处理
func ProcessValue(v interface{}) error {
    switch val := v.(type) {
    case string:
        return processString(val)
    case int:
        return processInt(val)
    case *User:
        return processUser(val)
    default:
        return errors.New("unsupported type")
    }
}
```

❌ **错误示例 - 使用反射**:
```go
// 使用反射 - 失去类型安全
func ProcessValue(v interface{}) error {
    val := reflect.ValueOf(v)

    switch val.Kind() {
    case reflect.String:
        str := val.String()
        return processString(str)
    case reflect.Int:
        i := val.Int()
        return processInt(int(i))
    case reflect.Ptr:
        // 复杂的类型判断
        if val.Elem().Type().Name() == "User" {
            return processUser(val.Interface().(*User))
        }
    }
    return nil
}
```

**原因**: 反射破坏类型安全，降低性能，增加复杂性。编译器无法检查反射代码的正确性。

---

**4.7.2** 不要滥用泛型 (Don't Overuse Generics)

泛型是工具，不是目标。只在类型无关的算法和数据结构中使用。

✅ **正确示例 - 适度使用泛型**:
```go
// 合理使用泛型 - 类型无关的容器
type Stack[T any] struct {
    items []T
}

func (s *Stack[T]) Push(item T) {
    s.items = append(s.items, item)
}

func (s *Stack[T]) Pop() (T, bool) {
    if len(s.items) == 0 {
        var zero T
        return zero, false
    }
    item := s.items[len(s.items)-1]
    s.items = s.items[:len(s.items)-1]
    return item, true
}

// 使用
stack := &Stack[int]{}
stack.Push(1)
```

❌ **错误示例 - 过度使用泛型**:
```go
// 过度泛型化 - 增加复杂性而无益处
type UserService[T User | *User, R UserRepository | *UserRepository] struct {
    repo R
}

func (s *UserService[T, R]) Create[C context.Context](ctx C, user T) error {
    // 泛型没有带来任何好处，只是增加复杂性
    return s.repo.Create(ctx, user)
}

// 使用变得复杂
service := &UserService[*User, *UserRepository]{repo: repo}
```

**原因**: 过度泛型化增加复杂性和编译时间，降低可读性。Go 的接口已经提供了足够的抽象。

---

**4.7.3** 优先使用标准库 (Prefer Standard Library)

标准库经过充分测试和优化。避免引入不必要的依赖。

✅ **正确示例 - 使用标准库**:
```go
import (
    "encoding/json"
    "net/http"
    "time"
)

func HandleRequest(w http.ResponseWriter, r *http.Request) {
    // 使用标准库的 JSON 编码
    data := map[string]string{"status": "ok"}
    w.Header().Set("Content-Type", "application/json")
    json.NewEncoder(w).Encode(data)
}

// 使用标准库的时间处理
func ScheduleTask(delay time.Duration) {
    timer := time.NewTimer(delay)
    <-timer.C
    executeTask()
}
```

❌ **错误示例 - 引入不必要的依赖**:
```go
import (
    "github.com/some/json-lib"      // 不必要的 JSON 库
    "github.com/another/time-lib"   // 不必要的时间库
    "github.com/fancy/http-wrapper" // 不必要的 HTTP 包装
)

func HandleRequest(w http.ResponseWriter, r *http.Request) {
    // 使用第三方库做标准库能做的事
    data := jsonlib.NewObject()
    data.Set("status", "ok")
    w.Header().Set("Content-Type", "application/json")
    jsonlib.Encode(w, data)
}
```

**原因**: 标准库稳定、经过充分测试、无需额外依赖。第三方库增加维护成本和安全风险。

---

**4.7.4** 避免过度抽象 (Avoid Over-Abstraction)

直接的代码优于抽象的代码。抽象应该来自实际需求，不是理论设计。

✅ **正确示例 - 直接清晰的代码**:
```go
// 直接的实现
func SendEmail(to, subject, body string) error {
    msg := &Email{
        To:      to,
        Subject: subject,
        Body:    body,
    }
    return smtpClient.Send(msg)
}

func SendSMS(phone, message string) error {
    return smsGateway.Send(phone, message)
}
```

❌ **错误示例 - 过度抽象**:
```go
// 过度抽象 - 为了"灵活性"
type MessageChannel interface {
    Send(recipient Recipient, content Content) error
}

type Recipient interface {
    GetDestination() string
    GetType() RecipientType
}

type Content interface {
    GetBody() string
    GetMetadata() map[string]interface{}
}

type MessageFactory interface {
    CreateMessage(channelType ChannelType, recipient Recipient, content Content) Message
}

type MessageDispatcher struct {
    factory  MessageFactory
    channels map[ChannelType]MessageChannel
}

// 发送一封邮件需要创建多个对象
func (d *MessageDispatcher) Dispatch(channelType ChannelType, recipient Recipient, content Content) error {
    msg := d.factory.CreateMessage(channelType, recipient, content)
    channel := d.channels[channelType]
    return channel.Send(msg.GetRecipient(), msg.GetContent())
}
```

**原因**: 过度抽象增加认知负担，降低可维护性。Go 哲学是"少即是多"，直接的代码更易理解。

---

**4.7.5** 保持包小而专注 (Keep Packages Small and Focused)

小包更易理解、测试和维护。一个包应该有单一的职责。

✅ **正确示例 - 小而专注的包**:
```go
// package email - 只负责邮件发送
package email

type Client struct {
    smtpHost string
    smtpPort int
}

func (c *Client) Send(to, subject, body string) error {
    // 邮件发送逻辑
    return nil
}

// package sms - 只负责短信发送
package sms

type Gateway struct {
    apiKey string
}

func (g *Gateway) Send(phone, message string) error {
    // 短信发送逻辑
    return nil
}
```

❌ **错误示例 - 大而全的包**:
```go
// package notification - 包含所有通知相关功能
package notification

// 邮件相关
type EmailClient struct{}
type EmailTemplate struct{}
type EmailQueue struct{}
type EmailRetry struct{}
type EmailTracking struct{}

// 短信相关
type SMSGateway struct{}
type SMSTemplate struct{}
type SMSQueue struct{}
type SMSRetry struct{}

// 推送通知相关
type PushService struct{}
type PushTemplate struct{}
type PushQueue struct{}

// 通知历史相关
type NotificationHistory struct{}
type NotificationAnalytics struct{}
type NotificationReport struct{}

// ... 数十个类型和函数
```

**原因**: 小包更易理解、测试和维护。大包违反单一职责原则，增加耦合。

---

### 4.8 Explicit Over Implicit 显式优先

Go 强调显式而非隐式。清晰的代码胜过聪明的代码。

**4.8.1** 显式错误处理 (Explicit Error Handling)

不要隐藏错误。每个错误都应该被显式处理或传播。

✅ **正确示例 - 显式错误处理**:
```go
func ProcessUser(ctx context.Context, userID int64) error {
    // 显式检查每个错误
    user, err := repo.GetByID(ctx, userID)
    if err != nil {
        return errors.Wrap(err, "failed to get user")
    }

    err = validator.Validate(user)
    if err != nil {
        return errors.Wrap(err, "validation failed")
    }

    err = service.Process(user)
    if err != nil {
        return errors.Wrap(err, "processing failed")
    }

    return nil
}
```

❌ **错误示例 - 隐式错误处理**:
```go
// 使用 panic/recover 隐藏错误
func ProcessUser(ctx context.Context, userID int64) (err error) {
    defer func() {
        if r := recover(); r != nil {
            err = errors.Errorf("panic: %v", r)
        }
    }()

    // 错误被 panic 隐藏
    user := mustGetUser(ctx, userID)      // 内部 panic
    mustValidate(user)                    // 内部 panic
    mustProcess(user)                     // 内部 panic

    return nil
}

func mustGetUser(ctx context.Context, userID int64) *User {
    user, err := repo.GetByID(ctx, userID)
    if err != nil {
        panic(err) // 隐藏错误
    }
    return user
}
```

**原因**: 显式错误处理使错误路径清晰可见。panic/recover 隐藏了错误流，降低代码可读性。

---

**4.8.2** 显式类型转换 (Explicit Type Conversion)

类型转换应该是显式的。避免隐式类型转换和自动装箱。

✅ **正确示例 - 显式类型转换**:
```go
func CalculateTotal(items []Item) int64 {
    var total int64
    for _, item := range items {
        // 显式类型转换
        price := int64(item.Price * 100)  // float64 -> int64
        quantity := int64(item.Quantity)  // int -> int64
        total += price * quantity
    }
    return total
}

func FormatPrice(cents int64) string {
    // 显式转换
    dollars := float64(cents) / 100.0
    return fmt.Sprintf("$%.2f", dollars)
}
```

❌ **错误示例 - 依赖隐式转换**:
```go
// 使用 interface{} 依赖运行时转换
func CalculateTotal(items []interface{}) interface{} {
    var total float64
    for _, item := range items {
        // 隐式依赖类型断言
        itemMap := item.(map[string]interface{})
        price := itemMap["price"].(float64)
        quantity := itemMap["quantity"].(float64)
        total += price * quantity
    }
    return total // 返回类型不明确
}
```

**原因**: 显式类型转换使类型关系清晰，编译器可以检查。隐式转换容易出错且难以发现。

---

**4.8.3** 显式初始化 (Explicit Initialization)

显式初始化变量，不要依赖零值的隐式行为（除非零值是有意义的默认值）。

✅ **正确示例 - 显式初始化**:
```go
func NewUserService(repo UserRepository) *UserService {
    return &UserService{
        repo:    repo,
        cache:   make(map[int64]*User),      // 显式初始化
        mu:      sync.RWMutex{},             // 显式初始化
        timeout: 30 * time.Second,            // 显式初始化
        enabled: true,                        // 显式初始化
    }
}

func ProcessOrder(order *Order) error {
    // 显式初始化局部变量
    totalPrice := 0.0
    totalItems := 0
    validatedItems := make([]*Item, 0, len(order.Items))

    // ...处理逻辑
    return nil
}
```

❌ **错误示例 - 依赖零值**:
```go
func NewUserService(repo UserRepository) *UserService {
    return &UserService{
        repo: repo,
        // cache: nil - 依赖零值，后续使用前需要检查
        // mu: sync.RWMutex{} - 依赖零值
        // timeout: 0 - 依赖零值，可能导致问题
        // enabled: false - 依赖零值，语义不明确
    }
}

func ProcessOrder(order *Order) error {
    var totalPrice float64  // 依赖零值，不如显式初始化
    var totalItems int      // 依赖零值
    var validatedItems []*Item  // nil，后续需要检查

    // ...处理逻辑
    return nil
}
```

**原因**: 显式初始化使意图清晰，避免因零值假设导致的 bug。代码自文档化。

---

**4.8.4** 显式依赖声明 (Explicit Dependency Declaration)

所有依赖应该通过参数或字段显式声明，不要使用全局变量或 init()。

✅ **正确示例 - 显式依赖**:
```go
// 依赖通过构造函数显式声明
type OrderService struct {
    userRepo    UserRepository
    productRepo ProductRepository
    paymentSvc  PaymentService
    notifier    Notifier
    logger      Logger
}

func NewOrderService(
    userRepo UserRepository,
    productRepo ProductRepository,
    paymentSvc PaymentService,
    notifier Notifier,
    logger Logger,
) *OrderService {
    return &OrderService{
        userRepo:    userRepo,
        productRepo: productRepo,
        paymentSvc:  paymentSvc,
        notifier:    notifier,
        logger:      logger,
    }
}

func (s *OrderService) CreateOrder(ctx context.Context, order *Order) error {
    // 所有依赖都是显式的
    user, err := s.userRepo.GetByID(ctx, order.UserID)
    if err != nil {
        s.logger.Error(ctx, "failed to get user", log.ErrorField(err))
        return err
    }
    // ...
    return nil
}
```

❌ **错误示例 - 隐式依赖**:
```go
// 全局变量 - 隐式依赖
var (
    globalUserRepo    UserRepository
    globalProductRepo ProductRepository
    globalPaymentSvc  PaymentService
    globalLogger      Logger
)

// init() 初始化全局变量 - 隐式初始化
func init() {
    db := connectDB()
    globalUserRepo = NewUserRepository(db)
    globalProductRepo = NewProductRepository(db)
    globalPaymentSvc = NewPaymentService()
    globalLogger = NewLogger()
}

type OrderService struct{}

func (s *OrderService) CreateOrder(ctx context.Context, order *Order) error {
    // 使用全局变量 - 依赖不清晰，难以测试
    user, err := globalUserRepo.GetByID(ctx, order.UserID)
    if err != nil {
        globalLogger.Error(ctx, "failed to get user", log.ErrorField(err))
        return err
    }
    // ...
    return nil
}
```

**原因**: 显式依赖使依赖关系清晰，便于测试（可注入 mock）。全局变量导致隐式耦合，难以测试。

---

**4.8.5** 显式控制流 (Explicit Control Flow)

控制流应该是显式的、自上而下的。避免使用 goto、隐式的控制流转移。

✅ **正确示例 - 显式控制流**:
```go
func ProcessTransaction(tx *Transaction) error {
    // 清晰的顺序控制流
    if err := validateTransaction(tx); err != nil {
        return errors.Wrap(err, "validation failed")
    }

    if err := checkBalance(tx); err != nil {
        return errors.Wrap(err, "insufficient balance")
    }

    if err := deductBalance(tx); err != nil {
        return errors.Wrap(err, "deduction failed")
    }

    if err := recordTransaction(tx); err != nil {
        // 显式的回滚逻辑
        rollbackErr := refundBalance(tx)
        if rollbackErr != nil {
            return errors.Wrapf(err, "record failed and rollback failed: %v", rollbackErr)
        }
        return errors.Wrap(err, "record failed")
    }

    return nil
}
```

❌ **错误示例 - 使用 goto**:
```go
func ProcessTransaction(tx *Transaction) error {
    if err := validateTransaction(tx); err != nil {
        goto handleError
    }

    if err := checkBalance(tx); err != nil {
        goto handleError
    }

    if err := deductBalance(tx); err != nil {
        goto rollback
    }

    if err := recordTransaction(tx); err != nil {
        goto rollback
    }

    return nil

rollback:
    refundBalance(tx)
    // 错误信息丢失

handleError:
    return errors.New("transaction failed") // 原始错误丢失
}
```

**原因**: 显式的顺序控制流易于理解和维护。goto 破坏了自上而下的阅读顺序，增加认知负担。

---

## Rule Reference by Category

### By Priority
- **P0 (Must Fix)**: Rules 1.1.* through 1.6.*
- **P1 (Strongly Recommended)**: Rules 2.1.* through 2.5.*, 4.1.* through 4.8.*
- **P2 (Suggested)**: Rules 3.1.* through 3.3.*

### By Domain
- **Error Handling**: 1.1.*
- **Safety**: 1.2.*
- **Database**: 1.3.*
- **Concurrency**: 1.4.*
- **JSON**: 1.5.*
- **Code Simplicity**: 1.6.*
- **Naming**: 2.1.*
- **Logging**: 2.2.*
- **Organization**: 2.3.*
- **Interfaces**: 2.4.*
- **Quality**: 2.5.*
- **Structure**: 3.1.*
- **Testing**: 3.2.*
- **Config**: 3.3.*
- **Design Philosophies**: 4.1.* through 4.8.*
  - **KISS**: 4.1.*
  - **DRY**: 4.2.*
  - **YAGNI**: 4.3.*
  - **SOLID**: 4.4.*
  - **LoD**: 4.5.*
  - **Composition**: 4.6.*
  - **Less is More**: 4.7.*
  - **Explicit Over Implicit**: 4.8.*

---

## Document History

- **v2.1.0** (2026-01-23): Enhanced logging standards with business context requirement
  - Added 1 new P1 rule (2.2.3.1): Log messages must describe business operations clearly
  - Rule requires log messages to have business meaning, not just technical descriptions
  - Emphasizes logs should tell the story of business flow without reading code
  - Provides guidelines for making error messages business-context aware
  - Updated total rules: 142 (P0: 38, P1: 94, P2: 10)

- **v2.0.0** (2026-01-20): Major change - Elevated code simplicity to P0
  - Created new P0 category: 1.6 Code Simplicity
  - Migrated 8 rules from P1 (2.5.*) to P0 (1.6.*):
    - 1.6.1 (formerly 2.5.2): Avoid magic numbers and strings
    - 1.6.2 (formerly 2.5.8): Allow pointer passing when data is already pointer type
    - 1.6.3 (formerly 2.5.9): Use proto utility functions
    - 1.6.4 (formerly 2.5.10): Avoid duplicate implementations
    - 1.6.5 (formerly 2.5.11): Use cache reasonably
    - 1.6.6 (formerly 2.5.12): Avoid unnecessary pointer operations
    - 1.6.7 (formerly 2.5.13): Optimize code execution order with Early Return
    - 1.6.8 (formerly 2.5.14): Prefer direct return over assignment with named returns
  - Renumbered remaining 2.5.* rules (2.5.3-2.5.7 became 2.5.2-2.5.6)
  - Updated total rules: 141 (P0: 38, P1: 93, P2: 10)
  - Breaking change: Code simplicity violations now require mandatory fixes

- **v1.3.3** (2026-01-20): Added return statement simplification
  - Added 1 new P1 rule (2.5.14): Prefer direct return over assignment with named returns
  - Rule promotes code simplicity by avoiding unnecessary error variable assignments
  - Clarifies that defer can correctly access directly returned values
  - Updated total rules: 141 (P0: 30, P1: 101, P2: 10)

- **v1.3.2** (2026-01-20): Added code simplicity improvements
  - Added 1 new P1 rule (2.5.12): Avoid unnecessary pointer operations
  - Rule prevents "address-of followed by dereference" anti-pattern
  - Encourages direct value usage when pointer conversion is unnecessary
  - Updated total rules: 140 (P0: 30, P1: 100, P2: 10)

- **v1.3.1** (2026-01-16): Added error creation best practices
  - Added 1 new P0 rule (1.1.6): Use appropriate error creation methods
  - Rule specifies using `errors.New()` for plain text and `errors.Errorf()` for parameterized errors
  - Explicitly forbids using `fmt.Errorf()` for error creation
  - Updated total rules: 139 (P0: 30, P1: 99, P2: 10)

- **v1.1.0** (2025-01-09): Added rules from GitLab MR reviews
  - Added 7 new P0 rules (1.1.5, 1.3.9-1.3.13, 1.5.2)
  - Added 8 new P1 rules (2.1.13-2.1.14, 2.3.15-2.3.16, 2.4.9-2.4.10, 2.5.9-2.5.11)
  - Added 5 new P2 rules (3.1.9-3.1.10, 3.2.4-3.2.7)
  - Enhanced existing rules with additional clarifications
  - Rules extracted from GitLab MR !7, !17, !27 code reviews

- **v1.0.0** (2025-01-16): Initial comprehensive standards document
  - Consolidated from original Go Code Review skill
  - Added rule numbering system
  - Organized by priority (P0/P1/P2) and category

---

**Maintained by**: FUTU Development Team
**Questions**: Contact team leads or post in #go-standards channel
